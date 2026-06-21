from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ReportConfig(BaseModel):
    max_charts: int = Field(default=3, ge=1, le=10)
    output_format: str = Field(default="json", pattern="^(json|html|pdf)$")
    llm_temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_retries: int = Field(default=2, ge=0, le=3)


class JobCreateRequest(BaseModel):
    dataset_id: str
    query: str = Field(min_length=10, max_length=2000)
    config: ReportConfig = Field(default_factory=ReportConfig)


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    estimated_duration_secs: int = 45


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress_pct: int | None = None
    current_node: str | None = None
    report_id: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
