# AutoInsight — The Layers of the Code (Plain-English Guide)

This explains the project one layer at a time, from the outside in. Each layer has:
**what it is**, **an everyday analogy**, **which files**, **what goes in / comes out**, and **the rule it follows**.

---

## The big picture: a restaurant

| Restaurant | AutoInsight layer |
|---|---|
| Front counter takes your order, gives you a ticket number | **API layer** (FastAPI) |
| The order form with required boxes | **Schema layer** (Pydantic) |
| Ticket rail between counter and kitchen | **Queue layer** (Redis + Celery) |
| Head chef following a recipe card, step by step | **Agent layer** (LangGraph) |
| Knives, oven, fridge the chef uses | **Tools layer** (LLM clients, sandbox, vector store) |
| Outside experts the chef phones (OpenAI, Anthropic) | **LLM layer** |
| Order book, pantry, recipe archive | **Data layer** (Postgres, files, Chroma) |
| House rules and settings on the wall | **Config & utilities layer** |
| The building, gas and electricity | **Infrastructure layer** (Docker, CI/CD) |

You place an order (upload a CSV and ask a question) and get a ticket (`job_id`). The kitchen works in the background. You check the ticket (`/status`), then pick up your meal (`/reports/{id}`).

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. API LAYER            app/main.py, app/api/                         │
│    receives HTTP, checks API key, reads/writes DB, enqueues jobs      │
├──────────────────────────────────────────────────────────────────────┤
│ 2. SCHEMA LAYER         app/schemas/                                  │
│    shapes & validation rules for every piece of data                  │
├──────────────────────────────────────────────────────────────────────┤
│ 3. QUEUE / WORKER LAYER app/workers/   (+ Redis)                      │
│    takes jobs off the queue, runs the agent, saves the result         │
├──────────────────────────────────────────────────────────────────────┤
│ 4. AGENT LAYER          app/pipeline/  (LangGraph, 11 nodes)          │
│    the "brain": profile → understand → plan → code → run → check →    │
│    write → assemble                                                   │
├──────────────────────────────────────────────────────────────────────┤
│ 5. TOOLS LAYER          app/tools/                                    │
│    LLM wrappers, safe code runner, vector search, chart rendering     │
├──────────────────────────────────────────────────────────────────────┤
│ 6. DATA LAYER           app/db/, alembic/, data/uploads/, chroma_db/  │
│    Postgres tables, uploaded CSVs, vector knowledge base              │
├──────────────────────────────────────────────────────────────────────┤
│ 7. CONFIG & UTILS       app/config.py, app/utils/, prompts/v1/        │
├──────────────────────────────────────────────────────────────────────┤
│ 8. INFRASTRUCTURE       Dockerfile, docker-compose.yml, .github/      │
└──────────────────────────────────────────────────────────────────────┘
```

**Golden rule of the layout:** upper layers call lower layers, never the other way round. Tools don't know about LangGraph. Nodes don't know about HTTP. The API never calls an LLM.

---

## Layer 1 — API layer

**What:** The front door. It speaks HTTP, checks who you are, saves small records and hands heavy work to the queue.
**Analogy:** The front counter. It takes your order and gives you a ticket, but never cooks.

**Files**
- `app/main.py`: `create_app()` builds the FastAPI app, adds CORS and logging middleware, and mounts routes at `/api/v1`.
- `app/api/routes.py`: the 9 endpoints (upload dataset, create job, job status, get/list reports, feedback, health).
- `app/api/deps.py`: shared helpers injected into routes. `verify_api_key()` is the bouncer and `get_db()` hands out a DB session that auto-commits.
- `app/api/middleware.py`: stamps every request with an `X-Request-ID` and logs how long it took.

**In:** HTTP requests (CSV file, JSON body, headers).
**Out:** JSON responses (ids, statuses, reports).

**Rule:** must answer fast. All slow LLM work is pushed to Layer 3. That's why `POST /jobs` returns `202 Accepted` right away.

Full route details: `docs/API_REFERENCE.md`.

---

## Layer 2 — Schema layer (data contracts)

**What:** Pydantic classes that describe the exact shape of data, with automatic validation.
**Analogy:** The order form. If "query" is shorter than 10 characters, the form is rejected before anyone acts on it.

**Files** (`app/schemas/`)
| File | Classes | Used for |
|---|---|---|
| `job.py` | `JobCreateRequest`, `ReportConfig`, `JobCreateResponse`, `JobStatusResponse`, `JobStatus` | API in/out |
| `data_profile.py` | `ColumnStat`, `DataProfile` | Output of the data profiler |
| `analysis.py` | `AnalysisGoal`, `AnalysisStep`, `AnalysisPlan` | Outputs of goal parser & planner |
| `report.py` | `CodeOutput`, `InsightBlock`, `ChartSpec`, `ReportOutput` | Sandbox result & the final report |

**How it's used:** a node builds a Pydantic object (which validates it), then calls `.model_dump()` to turn it into a plain dict for the graph state or the DB.

**Rule:** this is the single source of truth for data shapes. To change what a report looks like, start here.

---

## Layer 3 — Queue / worker layer

**What:** A background process that picks up jobs and runs the agent, so the API doesn't have to.
**Analogy:** The ticket rail (Redis) and the kitchen staff (Celery workers).

**Files**
- `app/workers/celery_app.py`: configures Celery (Redis address, time limits, one job at a time per worker slot).
- `app/workers/pipeline_task.py`: the one task, `run_agent_pipeline()`. It:
  1. marks the job `RUNNING`,
  2. builds and runs the graph, updating `current_node` as each node starts (`_run_graph()`),
  3. saves the report (`_store_report()`),
  4. marks the job `COMPLETED` (or `FAILED` with the error).

**In:** `(dataset_id, query, config)` from the queue. The task id equals the `job_id`.
**Out:** a row in `reports` and an updated row in `jobs`.

Deep dive: `docs/CELERY_GUIDE.md`.

---

## Layer 4 — Agent layer (the brain)

**What:** A LangGraph state machine. There are 11 small functions ("nodes") connected by arrows ("edges"). A shared dictionary ("state") flows through them, and each node adds its piece.
**Analogy:** A recipe card the head chef follows. Each step writes its result on a shared whiteboard (the state) for the next step to read. If a dish tastes wrong, the chef goes back a few steps and redoes it (the retry loop).

**Files**
- `app/pipeline/state.py`: `AgentState`, the list of everything that can be written on the whiteboard.
- `app/pipeline/graph.py`: `build_graph()` wires the nodes. `_should_retry()` decides what happens after code runs.
- `app/pipeline/<node>.py`: one file per step.

**The 11 steps in simple words**

| # | Node | In plain English | Uses AI? |
|---|---|---|---|
| 1 | `data_profiler` | "Open the CSV. What columns are there, what types, how many blanks, some example values?" | No (pandas) |
| 2 | `goal_parser` | "What is the user really asking? Which columns and chart types matter?" | GPT-4o-mini |
| 3 | `rag_retriever` | "Have we seen anything similar before? Fetch relevant notes from the knowledge base." | No (vector search) |
| 4 | `analysis_planner` | "Break the question into ≤5 concrete analysis steps." | GPT-4o |
| 5 | `code_writer` | "Write Python/pandas code that does those steps and saves charts." | GPT-4o |
| 6 | `code_executor` | "Run that code safely and capture what it printed and drew." | No (sandbox) |
| 7 | `self_critic` | "Does the output actually answer the question? Score it 0–10." | GPT-4o-mini |
| 8 | `validator` | "Good enough? If not, and we have retries left, go back to step 5." | No |
| 9 | `narrative_writer` | "Turn the numbers into an executive summary and insights." | Claude Sonnet |
| 10 | `assembler` | "Put summary, insights, charts and code into the final report format." | No |
| 11 | `rag_feedback_writer` | "Save this summary to the knowledge base so future questions benefit." | No |

**The loop:**
```
code_writer → code_executor → self_critic → validator ─┬─ good → narrative_writer → assembler → rag_feedback_writer
     ▲                                                 │
     └──────────────── not good & retries left ────────┘
code_executor fails & no retries left → straight to assembler (report without narrative)
```

**Rules**
- Every node is `function(state) -> dict` and returns **only what it adds**. LangGraph merges that into the state.
- Every key a node returns must be declared in `AgentState`.
- Nodes don't touch HTTP or the jobs table. That's Layer 3's job.

---

## Layer 5 — Tools layer

**What:** Reusable helpers that do real work. They know nothing about LangGraph, so you can test or reuse them anywhere.
**Analogy:** The kitchen equipment.

| File | Main functions | What it does |
|---|---|---|
| `llm_client.py` | `OpenAIClient.complete/complete_json`, `AnthropicClient.complete/complete_json`, `get_openai_client()`, `get_anthropic_client()` | One simple interface for both AI providers. Retries 3 times with backoff and parses JSON replies. |
| `sandbox.py` | `run_sandboxed_code()`, `_check_imports()`, `_list_charts()` | Runs AI-written Python safely: blocks unexpected imports, removes secrets from the environment, enforces a timeout, caps output size and detects new chart files. |
| `vector_store.py` | `ChromaVectorStore`, `DatabricksVectorStore`, `get_vector_store()` | "Search by meaning" in the knowledge base. Chroma locally, Databricks in prod. Drops weak matches below a 0.72 similarity score. |
| `chart_renderer.py` | `render_chart()`, `save_chart_png()` | Turns a `ChartSpec` into a Plotly chart. *Not wired in yet.* |

**Rule:** no LangGraph imports here. Secrets never go into the sandbox subprocess.

---

## Layer 6 — Data layer

**What:** Everywhere data is stored. There are three different stores, each for a different kind of data.
**Analogy:** The order book (Postgres), the pantry (uploaded CSV files) and the recipe archive (Chroma).

### 6a. PostgreSQL — records about things
Files: `app/db/base.py` (table classes), `app/db/session.py` (connection), `alembic/` (migrations that create the tables).

```
datasets ──< jobs ──< reports ──< feedback
```
| Table | One row = | Key columns |
|---|---|---|
| `datasets` | an uploaded CSV | `dataset_id`, `filename`, `s3_path` (local path for now), `size_bytes`, `status` |
| `jobs` | one question asked about a dataset | `job_id`, `dataset_id`, `query`, `status`, **`current_node`**, `error_message`, `report_id` |
| `reports` | a finished report | `report_id`, `job_id`, `dataset_id`, `report_json` (the whole report), `quality_score` |
| `feedback` | a user rating | `report_id`, `rating`, `comment` |

Who writes what:
- API writes `datasets`, `jobs` (create) and `feedback`.
- Worker writes `jobs` (status and progress) and `reports`.
- API reads everything for the GET endpoints.

### 6b. File storage — the actual data
- `data/uploads/<dataset_id>.csv`: written by `upload_dataset()`, read by `data_profiler_node` and inside the sandbox.
- `/tmp/charts/*.png`: written by the generated code inside the sandbox. Their paths end up in `report.charts[].s3_url`.
- (S3 settings exist in config. Moving uploads and charts to S3 is a planned next step.)

### 6c. Vector store (Chroma) — memory searched by meaning
- Folder: `./chroma_db` (setting `CHROMA_PERSIST_DIR`).
- Read by `rag_retriever_node`, written by `rag_feedback_writer_node`.
- It starts empty and fills up as reports are produced.

**Rule:** Postgres holds small metadata, files hold the big blobs, and Chroma holds searchable text.

---

## Layer 7 — Config & utilities

| File | What |
|---|---|
| `app/config.py` | `Settings`: every env var in one place (DB URL, Redis, API keys, sandbox limits, vector backend). `get_settings()` reads it once and caches it. |
| `.env.example` | Template. Copy it to `.env` and add your keys. |
| `prompts/v1/*.txt` | The system prompt for each AI node. Edit these to change AI behaviour, then restart the worker (prompts load at import time). |
| `app/utils/prompt_loader.py` | `load_prompt()` / `load_prompt_safe()` read those prompt files. |
| `app/utils/cost_tracker.py` | Token → $ calculator. *Not wired in yet.* |

---

## Layer 8 — Infrastructure

| File | What |
|---|---|
| `Dockerfile` | Builds one image used by both the API and the worker. |
| `docker-compose.yml` | Starts `postgres`, `redis`, `migrate` (creates tables, then exits), `api` (port 8000) and `worker`. |
| `Makefile` | Shortcuts: `make dev`, `make worker`, `make test`, `make check`, `make migrate`. |
| `.github/workflows/ci.yml` | Lint and tests on every push/PR. |
| `.github/workflows/cd.yml` | Builds and pushes the Docker image to Docker Hub. |

---

## One request through all layers

You upload `sales.csv` and ask *"Which category earned the most?"*

1. **API:** `upload_dataset()` saves `data/uploads/abc.csv` (Data, files) and inserts a `datasets` row (Data, Postgres).
2. **API + Schema:** `create_job()` validates the body with `JobCreateRequest`, inserts a `jobs` row (QUEUED) and puts a message on Redis (Queue). It replies `202 {job_id}`.
3. **Queue:** a Celery worker picks the message up and calls `run_agent_pipeline()`.
4. **Agent:** the graph runs 11 nodes, using **Tools** (LLM clients, sandbox, vector store). The worker updates `jobs.current_node` at every step.
5. **Data:** the worker saves the report into `reports` and sets the job to COMPLETED.
6. **API:** you poll `/jobs/{id}/status`, see COMPLETED with a `report_id`, and call `/reports/{report_id}`.

---

## Where do I change things?

| I want to… | Go to layer / file |
|---|---|
| Add a new endpoint | API → `app/api/routes.py` (+ schema in `app/schemas/`) |
| Change the report format | Schema → `app/schemas/report.py`, then `assembler_node` |
| Add a new agent step | Agent → new `app/pipeline/<x>.py`, add its keys to `state.py`, wire it in `graph.py` |
| Change what the AI is told | Config → `prompts/v1/<node>.txt` |
| Swap or upgrade an AI model | Tools → `llm_client.py` defaults, plus the model name inside the node |
| Add a DB column | Data → `app/db/base.py`, then `make migration msg="..."` and `make migrate` |
| Make the sandbox stricter | Tools → `app/tools/sandbox.py` |
| Change timeouts / worker concurrency | Queue → `app/workers/celery_app.py`, `Makefile`, `docker-compose.yml` |
