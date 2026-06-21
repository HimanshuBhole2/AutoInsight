"""Node 2: GOAL_PARSER — extract intent, target columns, chart types from query."""

from __future__ import annotations

from typing import Any

from app.schemas.analysis import AnalysisGoal
from app.utils.prompt_loader import load_prompt_safe

_SYSTEM = load_prompt_safe(
    "goal_parser",
    default=(
        "You are a data analyst assistant. Parse the user's analytical query and return JSON with keys: "
        "intent (str), target_columns (list[str]), chart_types (list[str]), time_range (str|null)."
    ),
)


def goal_parser_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.tools.llm_client import get_openai_client

    client = get_openai_client(model="gpt-4o-mini")
    profile = state.get("data_profile", {})
    col_names = [c["name"] for c in profile.get("columns", [])]

    raw = client.complete_json(
        messages=[
            {
                "role": "user",
                "content": (
                    f"Dataset columns: {col_names}\n\n"
                    f"User query: {state['query']}\n\n"
                    "Return JSON with keys: intent, target_columns, chart_types, time_range."
                ),
            }
        ],
        system=_SYSTEM,
        max_tokens=512,
    )

    goal = AnalysisGoal(
        intent=raw.get("intent", state["query"]),
        target_columns=raw.get("target_columns", []),
        chart_types=raw.get("chart_types", []),
        time_range=raw.get("time_range"),
    )

    return {"analysis_goal": goal.model_dump()}
