import asyncio
import uuid

import structlog
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.pool import NullPool

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
        _update_job_status(job_id, "RUNNING", current_node="data_profiler")

        from app.pipeline.graph import build_graph  # noqa: PLC0415

        graph = build_graph()
        initial_state = {
            "job_id": job_id,
            "dataset_id": dataset_id,
            "query": query,
            "config": config,
        }

        final_state = graph.invoke(initial_state)

        report_id = asyncio.run(
            _store_report(job_id, dataset_id, final_state.get("final_report") or {})
        )

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
    asyncio.run(_async_update_job(job_id, status, current_node, report_id, error))


async def _async_update_job(
    job_id: str,
    status: str,
    current_node: str | None,
    report_id: str | None,
    error: str | None,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: PLC0415

    from app.config import get_settings  # noqa: PLC0415
    from app.db.base import Job  # noqa: PLC0415

    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            job = await session.get(Job, job_id)
            if job:
                job.status = status
                if current_node is not None:
                    job.current_node = current_node
                if report_id is not None:
                    job.report_id = report_id
                if error is not None:
                    job.error_message = error
                await session.commit()
    finally:
        await engine.dispose()


async def _store_report(job_id: str, dataset_id: str, report_data: dict) -> str:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: PLC0415

    from app.config import get_settings  # noqa: PLC0415
    from app.db.base import Report  # noqa: PLC0415

    report_id = str(uuid.uuid4())
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            report = Report(
                report_id=report_id,
                job_id=job_id,
                dataset_id=dataset_id,
                report_json=report_data,
            )
            session.add(report)
            await session.commit()
    finally:
        await engine.dispose()
    return report_id
