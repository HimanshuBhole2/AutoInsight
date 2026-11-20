# 04 — Build Roadmap

Each phase ends with a **checkpoint**. Don't start the next phase until the checkpoint passes.
Times are rough guides — go at your own pace.

---

## Phase 0 — Setup (½–1 day)

- [ ] Create new repo `insight-agent` (or your chosen name), copy this plan to `docs/plan/`
- [ ] `uv init`, add pandas, pydantic, pytest, ruff, python-dotenv
- [ ] Create folders from [06_repo_layout.md](06_repo_layout.md)
- [ ] Put 3 test CSVs in `fixtures/data/` (see [05_io_testing.md](05_io_testing.md))
- [ ] Write `schemas.py` with **all** models from [02_agents.md](02_agents.md) (no logic yet)
- [ ] `tests/test_schemas.py`: each model builds from a sample dict

**Checkpoint:** `pytest` passes, `ruff check .` is clean.

---

## Phase 1 — The non-LLM agents (2–3 days)

Start without any LLM. These are the foundation and are 100% testable.

- [ ] **Profiler** — `agents/profiler.py` + CLI + I/O log on 5 CSVs
- [ ] **Executor** — `tools/sandbox.py` + `agents/executor.py` + the 7 sandbox test cases
- [ ] **Run recorder** — `core/recorder.py`: saves `input.json`, `output.json`, `meta.json`
      for every agent call into `runs/<run_id>/<agent>/`
- [ ] **Assembler** — citation regex + markdown builder + unit tests with fake narratives
- [ ] **Checker (rules only)** — 5 rules + unit tests

**Checkpoint:** you can hand-write pandas code for the question
"total revenue by region", run it through Executor → Checker → Assembler (with a hand-written
narrative), and get a valid `report.md`. **No LLM involved yet.**

---

## Phase 2 — The LLM agents, one at a time (5–7 days)

Build in this order. For each one: write prompt v1 → run 10–15 inputs → fill I/O log →
fix prompt → v2 → repeat until the "Done when" in 02_agents.md is met.

- [ ] `tools/llm.py` — one `complete_json()` method, token + cost tracking, a `FakeLLM` for tests
- [ ] **Goal Parser** — I/O log: 15 questions
- [ ] **Planner** — I/O log: same 15 questions (use saved Goal outputs as input)
- [ ] **Code Writer** — I/O log: every step from saved plans; run each through Executor
- [ ] **Code Writer retry** — feed Checker feedback back in; measure first-try vs after-retry
- [ ] **Narrator** — I/O log: 10 saved step_results sets; count invalid citations
- [ ] **Checker LLM part** (optional) — keep only if it helps

Tip: each agent's **saved outputs become the next agent's test inputs**. You never need to
re-run the whole chain to test one agent.

**Checkpoint:** each LLM agent meets its "Done when" from 02_agents.md.

---

## Phase 3 — Wire the pipeline (2–3 days)

- [ ] `pipeline/simple.py` — plain Python loop calling all 8 agents (≈ 40 lines)
- [ ] Run end-to-end on 10 question/CSV pairs, save every run
- [ ] `pipeline/graph.py` — same flow in LangGraph (nodes = thin wrappers around agents)
- [ ] Confirm LangGraph version gives the same results as the simple loop

**Checkpoint:** `python -m insight_agent run fixtures/data/sales.csv "Which region grew fastest?"`
produces `runs/<id>/report.md` with charts and valid citations.

---

## Phase 4 — Interface (2–3 days)

- [ ] CLI with `typer`: `insight run`, `insight show <run_id>`
- [ ] FastAPI: `POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/report`
- [ ] BackgroundTasks for async runs; status: queued → running → done/failed
- [ ] Optional: Streamlit page (upload, ask, view report)

**Checkpoint:** someone else can use it from a browser or curl.

---

## Phase 5 — Production basics (3–5 days)

- [ ] Dockerfile + docker-compose
- [ ] GitHub Actions: ruff + pytest on PRs
- [ ] SQLite → Postgres for run metadata (only if needed)
- [ ] Celery/RQ + Redis (only if BackgroundTasks is a real problem)

**Checkpoint:** `docker compose up` → working app; CI green.

---

## Phase 6 — Quality + RAG (1–2 weeks)

- [ ] `eval/run_eval.py` over 10–20 fixtures. Metrics:
  step success rate · citation validity · question answered (LLM judge or you) · cost · latency
- [ ] Track results per prompt version (MLflow or `eval/results.csv`)
- [ ] Tracing (LangSmith or OpenTelemetry)
- [ ] Knowledge Retriever + Memory Writer with Chroma — keep only if eval improves
- [ ] README with architecture diagram, eval table, demo GIF

**Checkpoint:** README shows real numbers, e.g.
"92% step success · 0 invalid citations · $0.04 / report · 18 s p50".

---

## Progress tracker

| Agent | Spec read | Code | CLI | I/O log | Done-when met |
|---|---|---|---|---|---|
| 1 Profiler | ☐ | ☐ | ☐ | ☐ | ☐ |
| 5 Executor | ☐ | ☐ | ☐ | ☐ | ☐ |
| 6 Checker (rules) | ☐ | ☐ | ☐ | ☐ | ☐ |
| 8 Assembler | ☐ | ☐ | ☐ | ☐ | ☐ |
| 2 Goal Parser | ☐ | ☐ | ☐ | ☐ | ☐ |
| 3 Planner | ☐ | ☐ | ☐ | ☐ | ☐ |
| 4 Code Writer | ☐ | ☐ | ☐ | ☐ | ☐ |
| 7 Narrator | ☐ | ☐ | ☐ | ☐ | ☐ |
| 9 Retriever | ☐ | ☐ | ☐ | ☐ | ☐ |
| 10 Memory Writer | ☐ | ☐ | ☐ | ☐ | ☐ |
