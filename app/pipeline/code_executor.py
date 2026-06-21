"""Node 6: CODE_EXECUTOR — run generated code in sandbox."""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.tools.sandbox import run_sandboxed_code


def code_executor_node(state: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    code = state.get("generated_code", "")
    csv_path = state.get("csv_path", f"data/uploads/{state['dataset_id']}.csv")

    result = run_sandboxed_code(
        code=code,
        csv_path=csv_path,
        timeout_seconds=settings.sandbox_timeout_seconds,
        max_memory_mb=settings.sandbox_max_memory_mb,
    )

    return {"execution_result": result.model_dump()}
