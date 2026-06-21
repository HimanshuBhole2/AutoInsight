from datetime import datetime

from pydantic import BaseModel, Field


class ChartSpec(BaseModel):
    chart_id: str
    title: str
    chart_type: str  # bar | line | scatter | pie | histogram
    x_col: str | None = None
    y_col: str | None = None
    color_col: str | None = None
    s3_url: str = ""
    description: str = ""


class InsightBlock(BaseModel):
    insight_id: str
    title: str
    body: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_data: dict = Field(default_factory=dict)


class CodeOutput(BaseModel):
    stdout: str
    stderr: str
    charts_generated: list[str] = Field(default_factory=list)
    execution_time_ms: int
    success: bool
    error: str | None = None


class ReportOutput(BaseModel):
    report_id: str
    job_id: str
    dataset_id: str
    query: str
    summary: str
    insights: list[InsightBlock] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    raw_code: str = ""
    rag_context_used: list[str] = Field(default_factory=list)
    model_versions: dict = Field(default_factory=dict)
    created_at: datetime
    quality_score: float | None = None
