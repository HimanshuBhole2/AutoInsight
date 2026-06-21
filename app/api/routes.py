from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, verify_api_key
from app.schemas.job import JobCreateRequest, JobCreateResponse, JobStatus, JobStatusResponse

router = APIRouter()


# ── Health ────────────────────────────────────────────────────────────────────


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await db.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB not ready: {exc}") from exc


# ── Datasets ──────────────────────────────────────────────────────────────────


@router.post("/datasets", status_code=201, dependencies=[Depends(verify_api_key)])
async def upload_dataset(file: UploadFile) -> dict:
    # Stub — full implementation in Phase 3
    return {"dataset_id": "stub", "filename": file.filename, "status": "READY"}


@router.get("/datasets/{dataset_id}", dependencies=[Depends(verify_api_key)])
async def get_dataset(dataset_id: str) -> dict:
    return {"dataset_id": dataset_id, "status": "READY"}


# ── Jobs ──────────────────────────────────────────────────────────────────────


@router.post(
    "/jobs",
    response_model=JobCreateResponse,
    status_code=202,
    dependencies=[Depends(verify_api_key)],
)
async def create_job(request: JobCreateRequest) -> JobCreateResponse:
    # Stub — Celery enqueue wired up in Phase 3
    return JobCreateResponse(job_id="stub-job-id", status=JobStatus.QUEUED)


@router.get(
    "/jobs/{job_id}/status",
    response_model=JobStatusResponse,
    dependencies=[Depends(verify_api_key)],
)
async def job_status(job_id: str) -> JobStatusResponse:
    from datetime import datetime

    return JobStatusResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )


# ── Reports ───────────────────────────────────────────────────────────────────


@router.get("/reports/{report_id}", dependencies=[Depends(verify_api_key)])
async def get_report(report_id: str) -> dict:
    return {"report_id": report_id, "status": "stub"}


@router.get("/reports", dependencies=[Depends(verify_api_key)])
async def list_reports(limit: int = 10, offset: int = 0) -> dict:
    return {"reports": [], "total": 0, "limit": limit, "offset": offset}


# ── Feedback ──────────────────────────────────────────────────────────────────


@router.post("/feedback/{report_id}", dependencies=[Depends(verify_api_key)])
async def submit_feedback(report_id: str, rating: int, comment: str = "") -> dict:
    return {"feedback_id": "stub", "report_id": report_id, "accepted": True}
