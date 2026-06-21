from enum import StrEnum

from pydantic import BaseModel, Field


class DatasetStatus(StrEnum):
    UPLOADING = "UPLOADING"
    READY = "READY"
    ERROR = "ERROR"


class ColumnStat(BaseModel):
    name: str
    dtype: str
    null_pct: float = Field(ge=0.0, le=1.0)
    unique_count: int | None = None
    sample_values: list[str] = Field(default_factory=list, max_length=5)
    min_val: str | None = None
    max_val: str | None = None


class DataProfile(BaseModel):
    dataset_id: str
    filename: str
    row_count: int
    col_count: int
    columns: list[ColumnStat]
    s3_path: str
    status: DatasetStatus = DatasetStatus.READY
    size_bytes: int = 0
