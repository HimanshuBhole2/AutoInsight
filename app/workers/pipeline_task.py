import structlog
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from app.workers.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(bind=True, name="run_agent_pipeline", max_retries=0)
def run_agent_pipeline(self: Task, dataset_id: str, query: str, config: dict) -> dict:
    """
    Idempotent Celery task that runs the full LangGraph pipeline.
    Returns {"status": "COMPLETED", "report_id": str} on success.
    """
    job_id: str = self.request.id or "local"
    log = logger.bind(job_id=job_id, dataset_id=dataset_id)

    try:
        log.info("pipeline_started")
        _update_job_status(job_id, "RUNNING", current_node="INTAKE")

        # Lazy import to avoid circular deps at module load
        from app.pipeline.graph import build_graph  # noqa: PLC0415

        graph = build_graph()
        initial_state = {
            "job_id": job_id,
            "dataset_id": dataset_id,
            "query": query,
            "config": config,
        }

        final_state = graph.invoke(initial_state)

        report_id = (final_state.get("final_report") or {}).get("report_id", "")
        _update_job_status(job_id, "COMPLETED", report_id=report_id)
        log.info("pipeline_completed", report_id=report_id)
        return {"status": "COMPLETED", "report_id": report_id}

    except SoftTimeLimitExceeded:
        _update_job_status(job_id, "FAILED", error="Pipeline timed out")
        log.error("pipeline_timeout")
        raise

    except Exception as exc:
        _update_job_status(job_id, "FAILED", error=str(exc))
        log.exception("pipeline_failed")
        raise


def _update_job_status(
    job_id: str,
    status: str,
    current_node: str | None = None,
    report_id: str | None = None,
    error: str | None = None,
) -> None:
    # Redis update wired in Phase 3; for now just log
    logger.info(
        "job_status_update",
        job_id=job_id,
        status=status,
        current_node=current_node,
        report_id=report_id,
    )
