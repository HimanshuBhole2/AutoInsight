"""Node 7: SELF_CRITIC — score code output quality, suggest retry if poor."""

from __future__ import annotations

from typing import Any

from app.utils.prompt_loader import load_prompt_safe

_SYSTEM = load_prompt_safe(
    "self_critic",
    default=(
        "You are a senior data analyst reviewing analysis output. "
        "Score it 0-10 on: relevance to query, correctness, completeness. "
        "Return JSON: {score: float, issues: list[str], verdict: 'pass'|'retry'}. "
        "Score < 6 or obvious errors → verdict='retry'."
    ),
)


def self_critic_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.tools.llm_client import get_openai_client

    execution_result = state.get("execution_result", {})
    if not execution_result.get("success"):
        # Execution already failed — no point critiquing output
        return {
            "critic_score": 0.0,
            "critic_verdict": "retry",
            "critic_issues": ["execution failed"],
        }

    client = get_openai_client(model="gpt-4o-mini")

    raw = client.complete_json(
        messages=[
            {
                "role": "user",
                "content": (
                    f"User query: {state['query']}\n\n"
                    f"Code output:\n{execution_result.get('stdout', '')}\n\n"
                    "Score this output. Return JSON with keys: score, issues, verdict."
                ),
            }
        ],
        system=_SYSTEM,
        max_tokens=512,
    )

    return {
        "critic_score": float(raw.get("score", 5.0)),
        "critic_verdict": raw.get("verdict", "pass"),
        "critic_issues": raw.get("issues", []),
    }
