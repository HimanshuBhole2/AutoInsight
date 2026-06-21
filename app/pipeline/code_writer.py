"""Node 5: CODE_WRITER — generate Pandas + Plotly analysis code."""

from __future__ import annotations

import json
import re
from typing import Any

from app.utils.prompt_loader import load_prompt_safe

_SYSTEM = load_prompt_safe(
    "code_writer",
    default=(
        "You are an expert data analyst. Write clean, executable Python code using Pandas and Matplotlib.\n"
        "Rules:\n"
        "- Variable 'df' is already loaded (DO NOT re-read the file)\n"
        "- Save charts to /tmp/charts/{chart_id}.png using plt.savefig()\n"
        "- Print key statistics to stdout\n"
        "- Do NOT use plt.show() — use plt.savefig() only\n"
        "- Handle missing values gracefully\n"
        "- Return only Python code, no markdown fences"
    ),
)


def code_writer_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.tools.llm_client import get_openai_client

    client = get_openai_client(model="gpt-4o")
    plan = state.get("analysis_plan", {})
    sample = state.get("dataset_sample", "")
    retry_count = state.get("retry_count", 0)
    prev_error = (state.get("execution_result") or {}).get("error", "")

    retry_ctx = ""
    if retry_count > 0 and prev_error:
        prev_code = state.get("generated_code", "")
        retry_ctx = (
            f"\n\nPrevious attempt failed.\nCode:\n```python\n{prev_code}\n```\n"
            f"Error:\n{prev_error}\n\nFix the error and return corrected code."
        )

    response = client.complete(
        messages=[
            {
                "role": "user",
                "content": (
                    f"Analysis steps:\n{json.dumps(plan.get('steps', []), indent=2)}\n\n"
                    f"Dataset sample (first 10 rows):\n{sample}\n"
                    f"{retry_ctx}"
                ),
            }
        ],
        system=_SYSTEM,
        max_tokens=2000,
        temperature=0.1,
    )

    code = response.strip()
    # Strip any markdown fences the model added despite instructions
    code = re.sub(r"```(?:python)?\n?", "", code).strip().rstrip("`").strip()

    return {
        "generated_code": code,
        "code_version": state.get("code_version", 0) + 1,
    }
