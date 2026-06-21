"""Node 11: RAG_FEEDBACK_WRITER — write report summary back to vector store for future retrieval."""

from __future__ import annotations

from typing import Any


def rag_feedback_writer_node(state: dict[str, Any]) -> dict[str, Any]:
    report = state.get("final_report") or {}
    summary = report.get("summary", "")
    query = state.get("query", "")

    if not summary:
        return {}

    try:
        from app.tools.vector_store import get_vector_store  # noqa: PLC0415

        vs = get_vector_store()
        doc = f"Query: {query}\nSummary: {summary}"
        vs.add_texts(
            texts=[doc],
            metadatas=[{"doc_type": "past_report", "job_id": state.get("job_id", "")}],
        )
    except Exception:
        # Non-critical — don't fail the pipeline over feedback write
        pass

    return {}
