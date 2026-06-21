"""Node 10: ASSEMBLER — assemble final ReportOutput from all node outputs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.schemas.report import ChartSpec, InsightBlock, ReportOutput


def assembler_node(state: dict[str, Any]) -> dict[str, Any]:
    synthesis = state.get("synthesis") or {}
    execution_result = state.get("execution_result") or {}
    job_id: str = state.get("job_id", "unknown")
    dataset_id: str = state.get("dataset_id", "unknown")

    insights = [
        InsightBlock(
            insight_id=i.get("insight_id", str(uuid.uuid4())[:8]),
            title=i.get("title", ""),
            body=i.get("body", ""),
            confidence=float(i.get("confidence", 0.7)),
            supporting_data=i.get("supporting_data", {}),
        )
        for i in synthesis.get("insights", [])
    ]

    charts = [
        ChartSpec(
            chart_id=str(uuid.uuid4())[:8],
            title=f"Chart {idx + 1}",
            chart_type="bar",
            s3_url=path,
        )
        for idx, path in enumerate(execution_result.get("charts_generated", []))
    ]

    report = ReportOutput(
        report_id=str(uuid.uuid4()),
        job_id=job_id,
        dataset_id=dataset_id,
        query=state.get("query", ""),
        summary=synthesis.get("summary", ""),
        insights=insights,
        charts=charts,
        raw_code=state.get("generated_code", ""),
        rag_context_used=state.get("rag_chunks", []),
        model_versions={"planner": "gpt-4o", "narrative": "claude-sonnet-4-6"},
        created_at=datetime.now(tz=UTC),
    )

    return {"final_report": report.model_dump(mode="json")}
