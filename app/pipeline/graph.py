"""LangGraph pipeline — wires all 11 nodes into a compiled graph."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.pipeline.analysis_planner import analysis_planner_node
from app.pipeline.assembler import assembler_node
from app.pipeline.code_executor import code_executor_node
from app.pipeline.code_writer import code_writer_node
from app.pipeline.data_profiler import data_profiler_node
from app.pipeline.goal_parser import goal_parser_node
from app.pipeline.narrative_writer import narrative_writer_node
from app.pipeline.rag_feedback_writer import rag_feedback_writer_node
from app.pipeline.rag_retriever import rag_retriever_node
from app.pipeline.self_critic import self_critic_node
from app.pipeline.validator import validator_node


def _should_retry(state: dict[str, Any]) -> str:
    """Retry code gen if execution failed and retries remain."""
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("config", {}).get("max_retries", 2)
    execution_ok = (state.get("execution_result") or {}).get("success", False)

    if not execution_ok and retry_count < max_retries:
        return "retry"
    if not execution_ok:
        return "fail"
    return "continue"


def build_graph() -> Any:
    graph = StateGraph(dict)

    graph.add_node("data_profiler", data_profiler_node)
    graph.add_node("goal_parser", goal_parser_node)
    graph.add_node("rag_retriever", rag_retriever_node)
    graph.add_node("analysis_planner", analysis_planner_node)
    graph.add_node("code_writer", code_writer_node)
    graph.add_node("code_executor", code_executor_node)
    graph.add_node("self_critic", self_critic_node)
    graph.add_node("validator", validator_node)
    graph.add_node("narrative_writer", narrative_writer_node)
    graph.add_node("assembler", assembler_node)
    graph.add_node("rag_feedback_writer", rag_feedback_writer_node)

    graph.set_entry_point("data_profiler")
    graph.add_edge("data_profiler", "goal_parser")
    graph.add_edge("goal_parser", "rag_retriever")
    graph.add_edge("rag_retriever", "analysis_planner")
    graph.add_edge("analysis_planner", "code_writer")
    graph.add_edge("code_writer", "code_executor")

    graph.add_conditional_edges(
        "code_executor",
        _should_retry,
        {"retry": "self_critic", "fail": "assembler", "continue": "self_critic"},
    )

    graph.add_edge("self_critic", "validator")
    graph.add_conditional_edges(
        "validator",
        lambda s: "retry" if s.get("should_retry") else "continue",
        {"retry": "code_writer", "continue": "narrative_writer"},
    )

    graph.add_edge("narrative_writer", "assembler")
    graph.add_edge("assembler", "rag_feedback_writer")
    graph.add_edge("rag_feedback_writer", END)

    return graph.compile()
