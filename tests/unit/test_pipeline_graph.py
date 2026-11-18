"""Graph wiring + worker helpers — no LLM, DB or Redis calls (all nodes faked)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.pipeline.graph as graph_mod

_NODE_ATTRS = [
    "data_profiler_node",
    "goal_parser_node",
    "rag_retriever_node",
    "analysis_planner_node",
    "code_writer_node",
    "code_executor_node",
    "self_critic_node",
    "narrative_writer_node",
    "assembler_node",
    "rag_feedback_writer_node",
]


@pytest.fixture
def fake_nodes(monkeypatch):
    """Replace every LLM/IO node with a fake that records the state it received."""
    seen: dict[str, dict] = {}

    def make(name, output):
        def _node(state):
            seen[name] = dict(state)
            return output(state) if callable(output) else output

        return _node

    outputs = {
        "data_profiler_node": {
            "data_profile": {"columns": []},
            "dataset_sample": "",
            "csv_path": "x.csv",
        },
        "goal_parser_node": {"analysis_goal": {"intent": "i"}},
        "rag_retriever_node": {"rag_chunks": [], "rag_query": "q"},
        "analysis_planner_node": {"analysis_plan": {"steps": []}},
        "code_writer_node": lambda s: {
            "generated_code": "print(1)",
            "code_version": s.get("code_version", 0) + 1,
        },
        "code_executor_node": {"execution_result": {"success": True, "stdout": "1"}},
        "self_critic_node": {"critic_score": 9.0, "critic_verdict": "pass", "critic_issues": []},
        "narrative_writer_node": {"synthesis": {"summary": "s", "insights": []}},
        "assembler_node": {"final_report": {"report_id": "rep-123", "summary": "s"}},
        "rag_feedback_writer_node": {},
    }
    for attr in _NODE_ATTRS:
        monkeypatch.setattr(graph_mod, attr, make(attr, outputs[attr]))
    return seen


def test_state_is_merged_across_nodes(fake_nodes):
    final = graph_mod.build_graph().invoke(
        {"job_id": "j", "dataset_id": "d", "query": "what is up?", "config": {"max_retries": 2}}
    )
    # Later nodes still see the initial input and earlier outputs
    assert fake_nodes["goal_parser_node"]["query"] == "what is up?"
    assert "data_profile" in fake_nodes["goal_parser_node"]
    assert "rag_chunks" in fake_nodes["narrative_writer_node"]
    # Final state keeps everything
    assert final["query"] == "what is up?"
    assert final["final_report"]["report_id"] == "rep-123"
    assert final["should_retry"] is False


def test_run_graph_reports_each_node_start(fake_nodes):
    from app.workers.pipeline_task import _run_graph

    started: list[str] = []
    final = _run_graph(
        graph_mod.build_graph(),
        {"job_id": "j", "dataset_id": "d", "query": "what is up?", "config": {}},
        on_node_start=started.append,
    )
    assert started == [
        "data_profiler",
        "goal_parser",
        "rag_retriever",
        "analysis_planner",
        "code_writer",
        "code_executor",
        "self_critic",
        "validator",
        "narrative_writer",
        "assembler",
        "rag_feedback_writer",
    ]
    assert final["final_report"]["report_id"] == "rep-123"


def test_critic_retry_loops_back_to_code_writer(fake_nodes, monkeypatch):
    verdicts = iter(["retry", "pass"])
    monkeypatch.setattr(
        graph_mod,
        "self_critic_node",
        lambda s: {"critic_score": 3.0, "critic_verdict": next(verdicts), "critic_issues": []},
    )
    final = graph_mod.build_graph().invoke(
        {"job_id": "j", "dataset_id": "d", "query": "what is up?", "config": {"max_retries": 2}}
    )
    assert final["code_version"] == 2
    assert final["retry_count"] == 1


def _patched_db():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=cm)
    engine = MagicMock()
    engine.dispose = AsyncMock()
    return session, engine, factory


def test_store_report_uses_assembler_report_id():
    from app.workers.pipeline_task import _store_report

    session, engine, factory = _patched_db()
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine),
        patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=factory),
    ):
        rid = asyncio.run(_store_report("job-1", "ds-1", {"report_id": "rep-123", "summary": "s"}))

    assert rid == "rep-123"
    stored = session.add.call_args.args[0]
    assert stored.report_id == "rep-123"
    assert stored.report_json["report_id"] == "rep-123"


def test_store_report_falls_back_to_new_id():
    from app.workers.pipeline_task import _store_report

    _, engine, factory = _patched_db()
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine),
        patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=factory),
    ):
        rid = asyncio.run(_store_report("job-1", "ds-1", {}))
    assert len(rid) == 36
