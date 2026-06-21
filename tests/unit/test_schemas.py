"""Pydantic schema validation tests."""

import pytest
from pydantic import ValidationError

from app.schemas.analysis import AnalysisGoal, AnalysisPlan, AnalysisStep
from app.schemas.data_profile import ColumnStat, DataProfile
from app.schemas.job import JobCreateRequest, JobStatus, ReportConfig
from app.schemas.report import CodeOutput, InsightBlock

# ── JobCreateRequest ──────────────────────────────────────────────────────────


def test_job_create_request_valid():
    req = JobCreateRequest(dataset_id="ds-123", query="What are the top 10 products by revenue?")
    assert req.dataset_id == "ds-123"
    assert req.config.max_charts == 3  # default


def test_job_create_request_query_too_short():
    with pytest.raises(ValidationError):
        JobCreateRequest(dataset_id="ds-123", query="short")


def test_job_create_request_query_too_long():
    with pytest.raises(ValidationError):
        JobCreateRequest(dataset_id="ds-123", query="x" * 2001)


def test_report_config_defaults():
    cfg = ReportConfig()
    assert cfg.max_charts == 3
    assert cfg.output_format == "json"
    assert cfg.llm_temperature == 0.2


def test_report_config_invalid_format():
    with pytest.raises(ValidationError):
        ReportConfig(output_format="xml")


def test_report_config_max_charts_clamped():
    with pytest.raises(ValidationError):
        ReportConfig(max_charts=11)


# ── DataProfile ───────────────────────────────────────────────────────────────


def test_column_stat_null_pct_range():
    with pytest.raises(ValidationError):
        ColumnStat(name="col", dtype="float64", null_pct=1.5)


def test_data_profile_valid():
    col = ColumnStat(name="price", dtype="float64", null_pct=0.05, sample_values=["1.0", "2.0"])
    profile = DataProfile(
        dataset_id="ds-1",
        filename="sales.csv",
        row_count=1000,
        col_count=1,
        columns=[col],
        s3_path="s3://bucket/key",
    )
    assert profile.row_count == 1000


# ── Report schemas ────────────────────────────────────────────────────────────


def test_insight_block_confidence_range():
    with pytest.raises(ValidationError):
        InsightBlock(
            insight_id="i1",
            title="Test",
            body="Some insight",
            confidence=1.5,
        )


def test_insight_block_valid():
    block = InsightBlock(
        insight_id="i1",
        title="Revenue trend",
        body="Revenue grew 12% YoY.",
        confidence=0.85,
        supporting_data={"revenue_growth": "12%"},
    )
    assert block.confidence == 0.85


def test_code_output_failed():
    out = CodeOutput(
        stdout="", stderr="NameError", execution_time_ms=100, success=False, error="NameError"
    )
    assert not out.success


# ── Analysis schemas ──────────────────────────────────────────────────────────


def test_analysis_goal_valid():
    goal = AnalysisGoal(
        intent="Identify top revenue products",
        target_columns=["product_name", "revenue"],
        chart_types=["bar"],
    )
    assert goal.time_range is None


def test_analysis_plan_steps():
    step = AnalysisStep(
        step_id="step_1",
        description="Aggregate revenue by product",
        sub_query="Which product has the highest revenue?",
        requires_code=True,
    )
    plan = AnalysisPlan(steps=[step])
    assert len(plan.steps) == 1


# ── JobStatus enum ────────────────────────────────────────────────────────────


def test_job_status_values():
    assert JobStatus.QUEUED == "QUEUED"
    assert JobStatus.COMPLETED == "COMPLETED"
    assert set(JobStatus) == {"QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"}
