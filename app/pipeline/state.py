"""AgentState — the shared state dict passed between LangGraph nodes.

Every key a node may return MUST be declared here. LangGraph creates one channel
per key and merges each node's partial return into the state. (With a plain
``StateGraph(dict)`` there is a single root channel, so each node's return would
*replace* the whole state and later nodes would lose ``query``, ``data_profile`` …)

``total=False``: keys appear progressively as nodes run.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # ── Initial input (set by the Celery worker) ──────────────────────────────
    job_id: str
    dataset_id: str
    query: str
    config: dict[str, Any]

    # ── data_profiler ─────────────────────────────────────────────────────────
    data_profile: dict[str, Any]
    dataset_sample: str
    csv_path: str

    # ── goal_parser ───────────────────────────────────────────────────────────
    analysis_goal: dict[str, Any]

    # ── rag_retriever ─────────────────────────────────────────────────────────
    rag_chunks: list[str]
    rag_query: str

    # ── analysis_planner ──────────────────────────────────────────────────────
    analysis_plan: dict[str, Any]

    # ── code_writer ───────────────────────────────────────────────────────────
    generated_code: str
    code_version: int

    # ── code_executor ─────────────────────────────────────────────────────────
    execution_result: dict[str, Any]

    # ── self_critic ───────────────────────────────────────────────────────────
    critic_score: float
    critic_verdict: str
    critic_issues: list[str]

    # ── validator ─────────────────────────────────────────────────────────────
    should_retry: bool
    retry_count: int

    # ── narrative_writer ──────────────────────────────────────────────────────
    synthesis: dict[str, Any]

    # ── assembler ─────────────────────────────────────────────────────────────
    final_report: dict[str, Any]
