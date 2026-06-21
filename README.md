# AutoInsight

Autonomous analytics agent: upload a CSV, ask a question, get a structured report with charts and insights — powered by a LangGraph pipeline, GPT-4o, Claude Sonnet, and RAG.

## Architecture

```
FastAPI (REST)  →  Celery (async jobs)  →  LangGraph pipeline (11 nodes)
                                               ↓
                     Data profiler → Goal parser → RAG retriever → Analysis planner
                     → Code writer → Code executor → Self-critic → Validator
                     → Narrative writer → Assembler → RAG feedback writer
```

Full design: see [AutoInsight_HLD_LLD.md](AutoInsight_HLD_LLD.md)

## Quick start

### Prerequisites
- Python 3.11+ (3.14 works; note psycopg2-binary needs `--pre` flag)
- Redis (for Celery)
- PostgreSQL (for job/report metadata)
- API keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`

### Local setup

```bash
# 1. Clone and enter repo
git clone https://github.com/HimanshuBhole2/AutoInsight.git
cd AutoInsight

# 2. Create virtualenv
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — fill in OPENAI_API_KEY and ANTHROPIC_API_KEY at minimum

# 5. Install pre-commit hooks
pre-commit install

# 6. Start infrastructure (Redis + Postgres)
make db      # docker run postgres
make redis   # docker run redis
# OR:
make up      # docker-compose up -d (starts everything)

# 7. Run database migrations
make migrate

# 8. Start the API
make dev     # uvicorn with hot-reload on :8000

# 9. (Optional) Start Celery worker in another terminal
make worker
```

The API is now live at http://localhost:8000. OpenAPI docs at http://localhost:8000/docs.

## Make targets

| Command | What it does |
|---|---|
| `make dev` | Start uvicorn with hot-reload |
| `make worker` | Start Celery worker (4 concurrent) |
| `make up` | `docker-compose up -d` (api + worker + redis + postgres + flower) |
| `make test` | Run unit tests |
| `make lint` | Run ruff |
| `make fmt` | Auto-format with black + ruff --fix |
| `make typecheck` | Run mypy |
| `make check` | lint + typecheck + test (full local CI) |
| `make eval` | Run 10-fixture eval harness (logs to MLflow) |
| `make bench` | p50/p95 latency benchmark per node |
| `make seed` | Seed Chroma vector store with starter knowledge base |
| `make migrate` | Run Alembic migrations |

## API usage

```bash
# Upload a dataset
curl -X POST http://localhost:8000/api/v1/datasets \
  -H "X-API-Key: dev-key-1" \
  -F "file=@sales.csv"
# → {"dataset_id": "...", "status": "READY"}

# Start a report job
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "X-API-Key: dev-key-1" \
  -H "Content-Type: application/json" \
  -d '{"dataset_id": "<id>", "query": "What are the top 10 products by revenue?"}'
# → {"job_id": "...", "status": "QUEUED"}

# Poll until COMPLETED
curl http://localhost:8000/api/v1/jobs/<job_id>/status \
  -H "X-API-Key: dev-key-1"

# Fetch the report
curl http://localhost:8000/api/v1/reports/<report_id> \
  -H "X-API-Key: dev-key-1"
```

## Branch workflow

```
main  ← protected: all CI checks must pass before merge
  └── day-N-<feature>  ← feature branches; open PR → CI runs → merge
```

**Rules on `main`:**
- Direct pushes blocked
- PR required with at least 1 approving review (can be bypassed for solo work)
- CI must be green: **ruff → mypy → pytest → docker build**

### Starting a new feature

```bash
git checkout main && git pull
git checkout -b day-3-<feature-name>
# ... make changes ...
git add <files>
git commit -m "feat: ..."
git push -u origin HEAD
gh pr create --fill   # opens PR; CI runs automatically
```

## Tech stack

| Layer | Choice |
|---|---|
| Orchestration | LangGraph (typed state machine) |
| LLMs | GPT-4o (planning, code gen) + Claude Sonnet (narrative, critique) |
| Embeddings | text-embedding-3-small |
| Vector store | Chroma (dev) / Databricks VSS (prod) |
| API | FastAPI + Mangum (Lambda adapter) |
| Async jobs | Celery + Redis |
| Database | PostgreSQL (SQLAlchemy async) |
| Observability | LangSmith traces + MLflow evals + Prometheus |
| CI/CD | GitHub Actions → AWS ECR → Lambda (API) / ECS (workers) |
| Code safety | AST import allowlist + subprocess env-stripping + timeout |

## Project structure

```
app/
  api/          FastAPI routes, auth, middleware
  db/           SQLAlchemy models + Alembic migrations
  pipeline/     11 LangGraph nodes (one file each)
  schemas/      Pydantic v2 contracts
  tools/        Reusable implementations (sandbox, vector store, LLM clients)
  utils/        Cost tracker, prompt loader
  workers/      Celery app + pipeline task
prompts/v1/     Versioned system prompts
eval/           10-fixture eval harness
tests/
  unit/         Fast, no external calls (34 tests)
  integration/  Requires running API + DB
```
