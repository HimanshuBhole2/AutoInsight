# AutoInsight — Claude Code Context

## What this project is
Autonomous analytics agent: user uploads CSV, asks a question, system produces a structured report
with charts, insights, and cited numbers. Portfolio project targeting Big Tech LLM/MLOps roles.

## Tech stack
- **Orchestration:** LangGraph (typed state machine, 11 nodes)
- **LLMs:** GPT-4o (planning, code gen) + Claude Sonnet (narrative, critique)
- **API:** FastAPI + Celery + Redis (async job queue)
- **DB:** PostgreSQL (metadata) + S3 (reports, charts, datasets)
- **RAG:** Chroma (dev) / Databricks VSS (prod) + text-embedding-3-small
- **Observability:** LangSmith traces + MLflow evals + Prometheus metrics

## Repo layout
- `app/` — main package (api, db, pipeline, schemas, tools, workers)
- `app/pipeline/` — one file per LangGraph node
- `app/tools/` — reusable implementations (no LangGraph deps)
- `app/schemas/` — Pydantic v2 contracts (source of truth for all data shapes)
- `tests/unit/` — fast, no external calls; `tests/integration/` — needs DB+Redis
- `eval/` — 10-fixture eval harness logging to MLflow
- `prompts/v1/` — versioned system prompts (change version when prompt changes)

## Key design decisions
- All heavy work goes through Celery — no synchronous LLM calls in HTTP handlers
- AgentState is immutable per node — each node returns a partial dict update
- Sandbox strips env vars before subprocess (no secrets leak to LLM-generated code)
- RAG score threshold 0.72 — below this is noise, don't inject garbage context
- ADRs in `docs/adr/` explain major trade-offs

## Common commands
```
make dev          # start uvicorn with hot-reload
make test         # unit tests only (fast)
make check        # lint + typecheck + unit tests
make eval         # run 10-fixture eval harness
make seed         # seed Chroma with starter knowledge base
```

## Environment
Copy `.env.example` → `.env` and fill in API keys before running anything.
`OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are required for pipeline nodes.
Everything else defaults to local dev values.

## Coding conventions
- Pydantic v2 (`model_dump()`, not `.dict()`)
- Async FastAPI endpoints; sync Celery tasks
- One node per file in `app/pipeline/`; nodes are pure functions `(state) → dict`
- Prompts live in `prompts/v1/*.txt` — never inline long prompts in code
- Never put secrets in subprocess env (see `app/tools/sandbox.py`)
