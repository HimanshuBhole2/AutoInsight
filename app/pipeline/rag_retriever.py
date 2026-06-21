"""Node 3: RAG_RETRIEVER — fetch relevant domain context from vector store."""

from __future__ import annotations

from typing import Any

from app.tools.vector_store import get_vector_store


def rag_retriever_node(state: dict[str, Any]) -> dict[str, Any]:
    goal = state.get("analysis_goal", {})
    rag_query = f"{state['query']} {goal.get('intent', '')}".strip()

    vs = get_vector_store()
    chunks = vs.similarity_search(query=rag_query, k=5, score_threshold=0.72)

    return {
        "rag_chunks": chunks,
        "rag_query": rag_query,
    }
