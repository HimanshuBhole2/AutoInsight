# 03 — Tools Plan

**Rule:** add a tool only in the phase where you need it. If you can't say what pain it
removes, don't add it yet. (The old repo added almost everything on day 1–4.)

## By phase

### Phase 0 — Setup (day 1)

| Tool | Why | Notes |
|---|---|---|
| Python 3.11+ | Language | 3.11 or 3.12 |
| `uv` | Fast venv + install | `uv init`, `uv add pandas` |
| `pandas`, `numpy` | Data work | Core of Profiler + generated code |
| `pydantic` v2 | All inputs/outputs | `model_dump()`, `model_validate()` |
| `pytest` | Tests | Start with unit tests only |
| `ruff` | Lint + format | One tool, one command |
| `python-dotenv` | Load API key from `.env` | Never commit `.env` |
| Git + GitHub | Version control | Small commits, one per agent milestone |

### Phase 1–2 — Agents (week 1–2)

| Tool | Used by | Why |
|---|---|---|
| **One LLM SDK** (`anthropic` *or* `openai`) | Goal Parser, Planner, Code Writer, Narrator, Checker | Start with one provider only. Wrap it in `llm.py` with one method: `complete_json(system, user, schema) -> BaseModel`. |
| `matplotlib` | Executor (charts) | Simple, works headless (`Agg`). Plotly later if you want interactive. |
| `subprocess` + `ast` (stdlib) | Executor | Sandbox: empty env, import allowlist, timeout. |
| `typer` (optional) | Every agent | Nice CLI for `python -m ... --input x.json`. `argparse` is fine too. |
| `rich` (optional) | I/O inspection | Pretty-print inputs/outputs in the terminal. |
| Jupyter notebook (optional) | Exploration | Good for poking an agent. Keep real code in `.py` files. |

### Phase 3 — Orchestration (week 3)

| Tool | Why |
|---|---|
| **LangGraph** | Wire the 8 agents into a graph with the retry loop. Only now — agents are already proven, so the graph is just "glue". |

Alternative: a plain Python `for` loop (`pipeline.py`) works too. Build the plain loop first
(30 lines), then port it to LangGraph. You'll understand LangGraph much better that way.

### Phase 4 — Interface (week 4)

| Tool | Why |
|---|---|
| CLI (`insight run data.csv "question"`) | First real "product". |
| **FastAPI** | `POST /runs` (upload CSV + question), `GET /runs/{id}`. |
| `BackgroundTasks` (FastAPI built-in) | Run the pipeline without blocking. Enough for a demo. |
| Streamlit *or* a tiny HTML page | Optional UI for demos/screenshots. |

### Phase 5 — Production (week 5–6)

| Tool | Add when… |
|---|---|
| Docker + docker-compose | You want others to run it with one command. |
| GitHub Actions CI | You have tests worth protecting (lint + unit tests on every PR). |
| Redis + Celery (or `arq`/RQ) | BackgroundTasks isn't enough (many jobs, restarts lose jobs). |
| PostgreSQL + SQLAlchemy + Alembic | You need to list past runs / users. SQLite is fine before that. |
| S3 / MinIO | Reports and charts must live outside one machine. Local disk before that. |

### Phase 6 — Quality and "Big Tech" polish (week 7–8)

| Tool | Why |
|---|---|
| **Eval harness** (your own script + 10–20 fixtures) | Measure: success rate, citation accuracy, cost, latency. |
| MLflow *or* a simple CSV/JSON results file | Compare prompt v1 vs v2 runs. |
| LangSmith *or* OpenTelemetry | Trace each agent call (helpful once there's a graph). |
| Chroma + an embedding model | Knowledge Retriever + Memory Writer (RAG). |
| Prometheus metrics | Only if you deploy it and want dashboards. |

## Tool decisions to make once (write the answer in your new README)

- [ ] LLM provider for v1: ______  (one only)
- [ ] Model for cheap agents (Goal Parser, Checker): ______
- [ ] Model for hard agents (Code Writer, Narrator): ______
- [ ] Charts: matplotlib (default) / plotly
- [ ] Orchestrator: plain loop → LangGraph (recommended path)

## Cost guard (from day 1)

Every LLM call records `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms` into
`meta.json`. Set a per-run budget (e.g. $0.25) and stop if exceeded. This also gives you real
numbers for your portfolio ("avg cost per report: $0.04").
