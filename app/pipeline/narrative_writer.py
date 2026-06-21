"""Node 9: NARRATIVE_WRITER — Claude Sonnet generates insight prose from execution output + RAG."""

from __future__ import annotations

from typing import Any

from app.utils.prompt_loader import load_prompt_safe

_SYSTEM = load_prompt_safe(
    "narrative_writer",
    default=(
        "You are a senior data analyst writing an executive summary. "
        "Combine statistical findings with domain context. Be precise, cite numbers. "
        "Return JSON: {summary: str, insights: [{insight_id, title, body, confidence, supporting_data}]}."
    ),
)


def narrative_writer_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.tools.llm_client import get_anthropic_client

    client = get_anthropic_client(model="claude-sonnet-4-6")
    execution_result = state.get("execution_result", {})
    rag_chunks = state.get("rag_chunks", [])
    rag_context = "\n\n".join(rag_chunks) if rag_chunks else "No domain context retrieved."

    raw = client.complete_json(
        messages=[
            {
                "role": "user",
                "content": (
                    f"User query: {state['query']}\n\n"
                    f"Code execution output:\n{execution_result.get('stdout', '')}\n\n"
                    f"Domain context:\n{rag_context}\n\n"
                    "Generate structured insights. Return only JSON."
                ),
            }
        ],
        system=_SYSTEM,
        max_tokens=2000,
    )

    return {"synthesis": raw}
