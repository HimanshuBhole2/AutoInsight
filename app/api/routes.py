import uuid
from pathlib import Path

import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, verify_api_key
from app.db.base import Dataset, Feedback, Job, Report
from app.schemas.job import JobCreateRequest, JobCreateResponse, JobStatus, JobStatusResponse

router = APIRouter()

_UPLOAD_DIR = Path("data/uploads")


# ── Health ────────────────────────────────────────────────────────────────────


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await db.execute(sqlalchemy.text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB not ready: {exc}") from exc


# ── Datasets ──────────────────────────────────────────────────────────────────


@router.post("/datasets", status_code=201, dependencies=[Depends(verify_api_key)])
async def upload_dataset(file: UploadFile, db: AsyncSession = Depends(get_db)) -> dict:
    dataset_id = str(uuid.uuid4())
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = _UPLOAD_DIR / f"{dataset_id}.csv"

    contents = await file.read()
    dest.write_bytes(contents)

    row = Dataset(
        dataset_id=dataset_id,
        filename=file.filename or "upload.csv",
        s3_path=str(dest),
        size_bytes=len(contents),
        status="READY",
    )
    db.add(row)
    await db.flush()

    return {"dataset_id": dataset_id, "filename": file.filename, "status": "READY"}


@router.get("/datasets/{dataset_id}", dependencies=[Depends(verify_api_key)])
async def get_dataset(dataset_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(Dataset, dataset_id)
    if not row:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {
        "dataset_id": row.dataset_id,
        "filename": row.filename,
        "status": row.status,
        "size_bytes": row.size_bytes,
    }


# ── Jobs ──────────────────────────────────────────────────────────────────────


@router.post(
    "/jobs",
    response_model=JobCreateResponse,
    status_code=202,
    dependencies=[Depends(verify_api_key)],
)
async def create_job(
    request: JobCreateRequest, db: AsyncSession = Depends(get_db)
) -> JobCreateResponse:
    dataset = await db.get(Dataset, request.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    job_id = str(uuid.uuid4())
    job = Job(
        job_id=job_id,
        dataset_id=request.dataset_id,
        query=request.query,
        config_json=request.config.model_dump(),
        status="QUEUED",
    )
    db.add(job)
    await db.flush()

    from app.workers.pipeline_task import run_agent_pipeline  # noqa: PLC0415

    run_agent_pipeline.apply_async(
        args=[request.dataset_id, request.query, request.config.model_dump()],
        task_id=job_id,
    )

    return JobCreateResponse(job_id=job_id, status=JobStatus.QUEUED)


@router.get(
    "/jobs/{job_id}/status",
    response_model=JobStatusResponse,
    dependencies=[Depends(verify_api_key)],
)
async def job_status(job_id: str, db: AsyncSession = Depends(get_db)) -> JobStatusResponse:
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job.job_id,
        status=JobStatus(job.status),
        current_node=job.current_node,
        report_id=job.report_id,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


# ── Reports ───────────────────────────────────────────────────────────────────


@router.get("/reports/{report_id}", dependencies=[Depends(verify_api_key)])
async def get_report(report_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(Report, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "report_id": row.report_id,
        "job_id": row.job_id,
        "dataset_id": row.dataset_id,
        "report": row.report_json,
    }


@router.get("/reports", dependencies=[Depends(verify_api_key)])
async def list_reports(
    limit: int = 10, offset: int = 0, db: AsyncSession = Depends(get_db)
) -> dict:
    result = await db.execute(
        select(Report).order_by(Report.created_at.desc()).limit(limit).offset(offset)
    )
    rows = result.scalars().all()
    return {
        "reports": [{"report_id": r.report_id, "job_id": r.job_id} for r in rows],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
    }


# ── Feedback ──────────────────────────────────────────────────────────────────


@router.post("/feedback/{report_id}", dependencies=[Depends(verify_api_key)])
async def submit_feedback(
    report_id: str, rating: int, comment: str = "", db: AsyncSession = Depends(get_db)
) -> dict:
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    fb = Feedback(report_id=report_id, rating=rating, comment=comment)
    db.add(fb)
    await db.flush()

    return {
        "feedback_id": str(fb.feedback_id) if fb.feedback_id else "pending",
        "report_id": report_id,
        "accepted": True,
    }
