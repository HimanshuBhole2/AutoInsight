from pydantic import BaseModel, Field


class AnalysisStep(BaseModel):
    step_id: str
    description: str
    sub_query: str
    requires_code: bool = True


class AnalysisPlan(BaseModel):
    steps: list[AnalysisStep] = Field(default_factory=list)


class AnalysisGoal(BaseModel):
    intent: str
    target_columns: list[str] = Field(default_factory=list)
    chart_types: list[str] = Field(default_factory=list)
    time_range: str | None = None
