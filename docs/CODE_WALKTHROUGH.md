# AutoInsight — Code Walkthrough

A function-by-function tour of the codebase, in the order a request actually flows.
The whole app is ~2,400 lines of Python, so you can read all of it in an afternoon.
Line references are clickable in most editors.

Companion docs: [API_REFERENCE.md](API_REFERENCE.md) (every route with examples) ·
[ARCHITECTURE_LAYERS.md](ARCHITECTURE_LAYERS.md) (plain-English layer guide) ·
[CELERY_GUIDE.md](CELERY_GUIDE.md) (how the background worker works).

---

## 0. The 30-second picture

```
 client ──HTTP──► FastAPI (app/api/routes.py)
                    │  1. POST /datasets  → save CSV to data/uploads/<id>.csv, row in `datasets`
                    │  2. POST /jobs      → row in `jobs` (QUEUED) + enqueue Celery task
                    ▼
                  Redis (broker)
                    ▼
             Celery worker (app/workers/pipeline_task.py)
                    │  graph.invoke(state)   ← LangGraph, 11 nodes (app/pipeline/*)
                    │  store final_report in `reports`, mark job COMPLETED
                    ▼
 client ──HTTP──► GET /jobs/{id}/status  → poll until COMPLETED, get report_id
                  GET /reports/{id}      → the JSON report
```

Two processes, one database:
- **API process** (`uvicorn app.main:app`) — never calls an LLM, only reads/writes Postgres and enqueues.
- **Worker process** (`celery -A app.workers.celery_app worker`) — runs the LangGraph pipeline.

---

## 1. Recommended reading order

| # | File | Why read it at this point |
|---|------|--------------------------|
| 1 | `app/config.py` | Every setting/env var the app uses |
| 2 | `app/schemas/*.py` | The data shapes everything else passes around |
| 3 | `app/db/base.py`, `app/db/session.py` | The 4 tables + how DB sessions are created |
| 4 | `app/main.py`, `app/api/*.py` | HTTP entry point |
| 5 | `app/workers/celery_app.py`, `pipeline_task.py` | How a job leaves the API and runs |
| 6 | `app/pipeline/state.py`, `app/pipeline/graph.py` | **The map** of the agent — read before any node |
| 7 | `app/pipeline/<node>.py` in graph order | Each step of the agent |
| 8 | `app/tools/*.py` | LLM wrappers, sandbox, vector store |
| 9 | `app/utils/*.py` | Prompt loading, cost tracking |
| 10 | `tests/unit/*.py` | Executable examples of how each piece is expected to behave |

---

## 2. Configuration — `app/config.py`

- **`class Settings(BaseSettings)`** — pydantic-settings reads every field from env vars (case-insensitive) or `.env`. E.g. `OPENAI_API_KEY` → `settings.openai_api_key`. Groups: app, database, redis/celery, LLM keys, S3, observability, vector store, sandbox limits.
- **`Settings.api_keys`** (property) — splits `VALID_API_KEYS="a,b"` into `["a","b"]`; used for auth.
- **`get_settings()`** — `@lru_cache`, so the env is read once per process. In tests, set env vars *before* first call (see `tests/conftest.py`).

---

## 3. Schemas — `app/schemas/`

Pydantic v2 models. They are the contract; nodes convert to dicts with `.model_dump()` before putting them in graph state.

**`job.py`**
- `JobStatus` — `QUEUED → RUNNING → COMPLETED | FAILED` (`CANCELLED` exists but nothing sets it).
- `ReportConfig` — per-job knobs. Only `max_retries` is actually read by the pipeline today; `max_charts`, `output_format`, `llm_temperature` are accepted but unused.
- `JobCreateRequest` — body of `POST /jobs` (`query` must be 10–2000 chars).
- `JobCreateResponse`, `JobStatusResponse` — API responses.

**`data_profile.py`** — `ColumnStat` (per-column stats) and `DataProfile` (whole dataset). Produced by the data_profiler node.

**`analysis.py`** — `AnalysisGoal` (goal_parser output), `AnalysisStep` / `AnalysisPlan` (analysis_planner output).

**`report.py`**
- `CodeOutput` — result of running generated code in the sandbox (`stdout`, `stderr`, `charts_generated`, `success`, `error`).
- `InsightBlock`, `ChartSpec` — pieces of the report.
- `ReportOutput` — the final report JSON stored in the DB.

---

## 4. Database — `app/db/`

**`base.py`**
- `Base` — SQLAlchemy declarative base (Alembic reads its metadata).
- `_now()`, `_uuid()` — column defaults.
- Tables: `Dataset` → `Job` (FK dataset) → `Report` (FK job, dataset) → `Feedback` (FK report).
  `Job.current_node`, `Job.error_message`, `Job.report_id` are how the worker reports progress back to the API.

**`session.py`**
- `_get_engine()` — lazily creates a single async engine (asyncpg) with pooling; SQL echo on in development.
- `_make_session_factory()` / `async_session_factory` — the session factory the API uses.

Schema migrations live in `alembic/versions/20260628_0001_create_core_tables.py`; `docker-compose` runs `alembic upgrade head` in the `migrate` service before the API starts.

---

## 5. HTTP layer — `app/main.py`, `app/api/`

**`main.py`**
- `lifespan(app)` — logs startup/shutdown. (Hook point for warming clients later.)
- `create_app()` — builds FastAPI, disables `/docs` in production, adds CORS (wide open) and `RequestLoggingMiddleware`, mounts the router at `/api/v1`, adds `GET /`.
- `app = create_app()` — module-level instance uvicorn imports.

**`middleware.py`**
- `RequestLoggingMiddleware.dispatch` — gives each request an 8-char id, logs start/finish with elapsed ms via structlog, returns it in the `X-Request-ID` header.

**`deps.py`** (FastAPI dependencies)
- `verify_api_key` — reads `X-API-Key` header; 401 unless it's in `settings.api_keys`.
- `get_db` — yields an `AsyncSession`; **commits automatically** after the handler returns, rolls back on exception. That's why handlers only call `db.flush()`.

**`routes.py`** — all endpoints:
| Function | Route | What it does |
|---|---|---|
| `health` | `GET /health` | Liveness, no deps |
| `readiness` | `GET /health/ready` | `SELECT 1` against Postgres, 503 if down |
| `upload_dataset` | `POST /datasets` | Writes upload to `data/uploads/<uuid>.csv`, inserts `Dataset` (the `s3_path` column currently holds a local path) |
| `get_dataset` | `GET /datasets/{id}` | Read one dataset row |
| `create_job` | `POST /jobs` | Validates dataset exists, inserts `Job(status=QUEUED)`, then `run_agent_pipeline.apply_async(..., task_id=job_id)` — **the Celery task id *is* the job id**, which is how the worker knows which row to update |
| `job_status` | `GET /jobs/{id}/status` | Reads the `Job` row the worker updates |
| `get_report` | `GET /reports/{id}` | Returns stored `report_json` |
| `list_reports` | `GET /reports` | Paginated list (`total` is page size, not a real count) |
| `submit_feedback` | `POST /feedback/{report_id}` | Inserts `Feedback(rating, comment)` from query params |

---

## 6. Background worker — `app/workers/`

**`celery_app.py`** — creates the `Celery` app (Redis broker/backend), JSON serialization, hard limit 300 s / soft limit 240 s per task, prefetch 1 (one long job per worker slot), recycle workers after 50 tasks.

**`pipeline_task.py`**
- `run_agent_pipeline(self, dataset_id, query, config)` — **the bridge between the API and the agent.**
  1. `job_id = self.request.id` (same as the DB row id).
  2. Marks job `RUNNING`.
  3. `build_graph()` then `_run_graph(graph, initial_state, on_node_start)` with `{job_id, dataset_id, query, config}`. Each time a node starts, `jobs.current_node` is updated so `GET /jobs/{id}/status` shows live progress.
  4. `_store_report(...)` saves `final_state["final_report"]` into `reports`, using the assembler's `report_id` as the row id.
  5. Marks job `COMPLETED` with `report_id`. On `SoftTimeLimitExceeded` or any exception → `FAILED` + error message, then re-raises.
- `_run_graph(graph, initial_state, on_node_start)` — runs `graph.stream(..., stream_mode=["tasks", "values"])`; a `"tasks"` event with `"input"` means "node X just started" → callback; the last `"values"` event is the final state (same as `invoke()`).
- `_update_job_status(...)` — sync wrapper: `asyncio.run(_async_update_job(...))` because Celery tasks are sync but the DB layer is async.
- `_async_update_job(...)` — makes a throwaway engine with `NullPool` (no pooled connections leaking across `asyncio.run` event loops), updates the `Job` row.
- `_store_report(...)` — same pattern; inserts a `Report` row (id = `report_data["report_id"]`, or a new uuid if missing) and returns its id.

---

## 7. The agent graph — `app/pipeline/graph.py`  ⭐ read this first

### State
The graph is built with `StateGraph(AgentState)`, where `AgentState` is a `TypedDict` declared in `app/pipeline/state.py`. Each node is `node(state) -> dict` and returns **only the keys it changes**; LangGraph keeps one channel per declared key and merges the returned keys into the state.

> Why the TypedDict matters: with `StateGraph(dict)` LangGraph has a single root channel, so each node's return value *replaces* the whole state, and the next node would lose `query`, `data_profile`, etc. Any new key a node returns must be added to `AgentState`.

This table is the single most useful thing for understanding the pipeline:

| State key | Written by | Read by |
|---|---|---|
| `job_id`, `dataset_id`, `query`, `config` | initial state (worker) | many |
| `data_profile`, `dataset_sample`, `csv_path` | data_profiler | goal_parser, analysis_planner, code_writer, code_executor |
| `analysis_goal` | goal_parser | rag_retriever |
| `rag_chunks`, `rag_query` | rag_retriever | analysis_planner, narrative_writer, assembler |
| `analysis_plan` | analysis_planner | code_writer |
| `generated_code`, `code_version` | code_writer | code_executor, code_writer (on retry), assembler |
| `execution_result` | code_executor | `_should_retry`, self_critic, code_writer (on retry), narrative_writer, assembler |
| `critic_score`, `critic_verdict`, `critic_issues` | self_critic | validator |
| `should_retry`, `retry_count` | validator | graph edge, code_writer, `_should_retry` |
| `synthesis` | narrative_writer | assembler |
| `final_report` | assembler | rag_feedback_writer, worker |

### Flow
```
data_profiler → goal_parser → rag_retriever → analysis_planner → code_writer → code_executor
                                                                     ▲              │ _should_retry
                                                                     │       ┌──────┴───────┐
                                                                     │  retry/continue     fail
                                                                     │       ▼              │
                                                                     │  self_critic         │
                                                                     │       ▼              │
                                                       should_retry  └── validator          │
                                                                             │ continue     │
                                                                             ▼              │
                                                                     narrative_writer       │
                                                                             ▼              ▼
                                                                          assembler ◄───────┘
                                                                             ▼
                                                                    rag_feedback_writer → END
```

- `_should_retry(state)` — after execution: `"fail"` if code failed and retries are exhausted (skips straight to assembler → a report with no narrative), otherwise both `"retry"` and `"continue"` go to self_critic.
- The **real retry loop** is `validator → code_writer`, driven by `should_retry`.
- `build_graph()` — registers the 11 nodes, wires the edges above, returns the compiled graph.

---

## 8. The nodes — `app/pipeline/` (in execution order)

Each node is a pure-ish function: read state → maybe call LLM/tool → return a partial dict. System prompts come from `prompts/v1/<node>.txt` via `load_prompt_safe`, with an inline fallback string if the file is missing.

1. **`data_profiler_node`** (`data_profiler.py`) — `pd.read_csv("data/uploads/<id>.csv")`; for every column computes dtype, null %, unique count, 5 sample values, min/max for numerics → `DataProfile`. Also `dataset_sample` = first 10 rows as a markdown table (needs `tabulate`). No LLM.
2. **`goal_parser_node`** — GPT-4o-mini, JSON mode. Input: column names + query. Output: `AnalysisGoal` (intent, target columns, chart types, time range).
3. **`rag_retriever_node`** — builds `rag_query = query + intent`, calls `get_vector_store().similarity_search(k=5, score_threshold=0.72)`. Returns a list of text chunks (may be empty). No LLM call here (Chroma embeds the query itself).
4. **`analysis_planner_node`** — GPT-4o, JSON mode. Input: full column schema + query + RAG context. Output: `AnalysisPlan` with ≤5 `AnalysisStep`s.
5. **`code_writer_node`** — GPT-4o, plain text, temp 0.1. Input: plan steps + 10-row sample. On retry, appends the previous code and its error and asks for a fix. Strips ``` fences with a regex. Output: `generated_code`, bumps `code_version`.
6. **`code_executor_node`** — calls `run_sandboxed_code(code, csv_path, timeout, memory)` → `execution_result` (a `CodeOutput` dict).
7. **`self_critic_node`** — if execution failed, short-circuits to `verdict="retry"`, score 0. Else GPT-4o-mini grades the **stdout** against the query → `critic_score`, `critic_verdict` (`pass`/`retry`), `critic_issues`.
8. **`validator_node`** — no LLM. `should_retry = verdict == "retry" and retry_count < max_retries`; increments `retry_count` when retrying.
9. **`narrative_writer_node`** — Claude Sonnet. Input: query + stdout + RAG context. Output: `synthesis = {summary, insights:[...]}`.
10. **`assembler_node`** — no LLM. Turns `synthesis.insights` into `InsightBlock`s, each path in `execution_result.charts_generated` into a `ChartSpec` (title "Chart N", type hard-coded `"bar"`), and builds `ReportOutput` → `final_report` (JSON-safe dict).
11. **`rag_feedback_writer_node`** — writes `"Query: …\nSummary: …"` back to the vector store as a `past_report` doc so future similar questions retrieve it. Swallows all errors (non-critical).

---

## 9. Tools — `app/tools/` (no LangGraph imports; reusable)

**`llm_client.py`**
- `OpenAIClient.complete(messages, system, max_tokens, temperature, json_mode)` — prepends system message, calls Chat Completions, sets `response_format=json_object` when `json_mode`. Wrapped in tenacity: 3 attempts, exponential backoff.
- `OpenAIClient.complete_json(...)` — `complete(json_mode=True)` + `json.loads`.
- `AnthropicClient.complete(...)` — Messages API, `system` passed as top-level param. Same retry policy.
- `AnthropicClient.complete_json(...)` — no native JSON mode, so it strips a leading ```json fence then `json.loads`.
- `get_openai_client(model)`, `get_anthropic_client(model)` — `lru_cache(maxsize=1)` factories. Note: because goal_parser/self_critic use `gpt-4o-mini` and planner/code_writer use `gpt-4o`, the 1-slot cache evicts on almost every call — still correct, just recreates the client.

**`sandbox.py`** — runs untrusted LLM code.
- `_ALLOWED_IMPORTS` — allowlist (pandas, numpy, matplotlib, plotly, json, math, re, os, …).
- `_SAFE_HEADER` — prepended to every script: imports pandas/matplotlib (Agg backend), creates `/tmp/charts`, loads `df = pd.read_csv(csv_path)`. That's why the prompt says "`df` is already loaded".
- `_check_imports(code)` — parses the code with `ast` and returns any `import`/`from` whose root module isn't allowlisted. (Despite the docstring it's an AST check, not RestrictedPython.)
- `run_sandboxed_code(code, csv_path, timeout_seconds, max_memory_mb)` —
  1. reject banned imports early;
  2. write header+code to a temp `.py`;
  3. build a minimal env (`PATH`, `HOME=/tmp`, `MPLBACKEND`) so API keys never reach the child process;
  4. snapshot `/tmp/charts/*.png`, run `python tmp.py` with timeout, diff the snapshot to find new charts;
  5. return `CodeOutput` with stdout/stderr capped at 8 KB / 2 KB; delete temp file.
  `max_memory_mb` is accepted but not enforced yet.
- `_list_charts()` — lists PNGs in `/tmp/charts`.

**`vector_store.py`**
- `VectorStore` — a `Protocol` (interface): `similarity_search`, `add_texts`.
- `ChromaVectorStore` — persistent local Chroma collection `autoinsight_knowledge_base`, cosine space. `similarity_search` converts Chroma's distance (0..2) to similarity `1 - d/2` and filters by threshold. `add_texts` upserts with md5(text) ids (so identical text dedupes). Chroma uses its built-in default embedding model, not `text-embedding-3-small`.
- `DatabricksVectorStore` — prod backend; search only, `add_texts` raises `NotImplementedError` (the feedback node swallows that).
- `get_vector_store()` — cached factory choosing backend from `VECTOR_STORE_BACKEND`.

**`chart_renderer.py`** — `render_chart(spec, df)` → Plotly figure by `chart_type`; `fig_to_html`, `fig_to_png_bytes`, `save_chart_png`. **Not called anywhere yet** — charts currently come from matplotlib inside the sandbox.

---

## 10. Utilities — `app/utils/`

- **`prompt_loader.py`** — `load_prompt(name, version="v1")` reads `prompts/v1/<name>.txt` (cached); `load_prompt_safe` returns a default instead of raising. Node modules call this **at import time**, so editing a prompt requires restarting the worker.
- **`cost_tracker.py`** — `ModelUsage.cost_usd`, `RunCostTracker.record/summary` with a price table. **Not wired in yet.**

---

## 11. How to actually learn it (hands-on)

1. **Run the tests and read them alongside the code** — they're the fastest spec:
   ```bash
   pytest tests/unit -v
   ```
   `test_sandbox.py` shows sandbox behavior; `test_smoke.py` shows API routes with a mocked DB; `test_schemas.py` shows validation rules.
2. **Run the pipeline without Celery/HTTP** — drop a CSV in `data/uploads/demo.csv` and from a Python shell (with `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` set):
   ```python
   from app.pipeline.graph import build_graph
   g = build_graph()
   for step in g.stream({"job_id": "local", "dataset_id": "demo",
                         "query": "Which product category has the highest revenue?",
                         "config": {"max_retries": 2}}):
       print(list(step.keys())[0], "→", list(next(iter(step.values())).keys()))
   ```
   `stream()` prints each node as it runs and the keys it wrote — a live version of the state table above.
3. **Run a single node** — every node is a function of a dict, e.g. `data_profiler_node({"dataset_id": "demo"})`. Feed its output into the next one to step through manually.
4. **Full stack** — `docker-compose up`, then `POST /api/v1/datasets` (multipart file) → `POST /api/v1/jobs` → poll `/jobs/{id}/status` → `GET /reports/{id}`, all with header `X-API-Key: dev-key-1`. Swagger UI at `http://localhost:8000/docs`.
5. **Watch LLM calls** — set `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` to see each node in LangSmith.

---

## 12. Known gaps / things that will confuse you while reading

Fixed so far: graph state merging (`AgentState`), matching report ids, and per-node `current_node` updates (covered by `tests/unit/test_pipeline_graph.py`). Still open:

- **Charts are local paths** in `/tmp/charts` (not S3); `ChartSpec.chart_type` is always `"bar"`; `chart_renderer.py` is unused.
- **Sandbox allowlists `os`**, so generated code can still call `os.system(...)`; env stripping is the main protection. It also runs `python` from `PATH` rather than the worker's own interpreter, and doesn't enforce `max_memory_mb`.
- **`ReportConfig`** fields other than `max_retries` are ignored; `cost_tracker.py` isn't used; `quality_score` on `Report` is never set (the critic score could go there).
- **Referenced but missing:** `docs/adr/`, `eval/harness.py`, `scripts/seed_vectorstore.py`, `scripts/generate_data.py`, `bench/` — `make eval/seed/gendata/bench` will fail. With an empty Chroma DB, RAG returns nothing until a few reports have been written back by node 11.
