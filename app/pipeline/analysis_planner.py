"""Node 4: ANALYSIS_PLANNER — decompose query into ordered analysis steps."""

from __future__ import annotations

import json
from typing import Any

from app.schemas.analysis import AnalysisPlan, AnalysisStep
from app.utils.prompt_loader import load_prompt_safe

_SYSTEM = load_prompt_safe(
    "analysis_planner",
    default=(
        "You are a senior data analyst. Given a dataset schema and user query, produce a JSON object "
        "with key 'steps': list of {step_id, description, sub_query, requires_code}. "
        "Max 5 steps. Be specific about what each step computes."
    ),
)


def analysis_planner_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.tools.llm_client import get_openai_client

    client = get_openai_client(model="gpt-4o")
    profile = state.get("data_profile", {})
    rag_context = "\n\n".join(state.get("rag_chunks", []))

    raw = client.complete_json(
        messages=[
            {
                "role": "user",
                "content": (
                    f"Dataset schema:\n{json.dumps(profile.get('columns', []), indent=2)}\n\n"
                    f"User query: {state['query']}\n\n"
                    f"Domain context:\n{rag_context or 'none'}\n\n"
                    "Return JSON with key 'steps'."
                ),
            }
        ],
        system=_SYSTEM,
        max_tokens=1000,
    )

    steps = [
        AnalysisStep(
            step_id=s.get("step_id", f"step_{i}"),
            description=s.get("description", ""),
            sub_query=s.get("sub_query", ""),
            requires_code=s.get("requires_code", True),
        )
        for i, s in enumerate(raw.get("steps", []))
    ]

    plan = AnalysisPlan(steps=steps)
    return {"analysis_plan": plan.model_dump()}
