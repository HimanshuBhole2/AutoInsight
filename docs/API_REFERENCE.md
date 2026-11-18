# AutoInsight — API Reference

Every HTTP route the app exposes: what it needs, what it returns, example calls, and **which functions produce the output** (including the LangGraph nodes behind the report).

- Base URL (local): `http://localhost:8000`
- All business routes are under the prefix **`/api/v1`** (mounted in `create_app()` in `app/main.py`).
- Interactive docs (non-production only): `http://localhost:8000/docs` (Swagger) and `/redoc`.

---

## 1. Common rules for every route

### Authentication
Routes marked 🔒 need the header:
```
X-API-Key: dev-key-1
```
Valid keys come from the `VALID_API_KEYS` env var (comma-separated, default `dev-key-1`).
Checked by `verify_api_key()` in `app/api/deps.py`.

| Situation | Status | Body |
|---|---|---|
| Header missing | `422` | FastAPI validation error (`"loc": ["header", "X-API-Key"]`) |
| Header present but wrong | `401` | `{"detail": "Invalid API key"}` |

### Database session
Handlers receive `db` from `get_db()` (`app/api/deps.py`). It **commits automatically** after the handler returns and rolls back if it raises. So handlers only call `db.flush()`.

### Response header
Every response gets `X-Request-ID: <8 chars>` from `RequestLoggingMiddleware.dispatch()` (`app/api/middleware.py`). Search the logs for this id to find the request.

### Validation errors (any route)
If the request body or params don't match the schema, FastAPI returns `422`:
```json
{
  "detail": [
    {"type": "string_too_short", "loc": ["body", "query"], "msg": "String should have at least 10 characters", "input": "hi"}
  ]
}
```

---

## 2. Route summary

| Method | Path | Auth | Handler (`app/api/routes.py`) | Purpose |
|---|---|---|---|---|
| GET | `/` | – | `root()` in `app/main.py` | App alive + version |
| GET | `/api/v1/health` | – | `health()` | Liveness |
| GET | `/api/v1/health/ready` | – | `readiness()` | Is Postgres reachable? |
| POST | `/api/v1/datasets` | 🔒 | `upload_dataset()` | Upload a CSV |
| GET | `/api/v1/datasets/{dataset_id}` | 🔒 | `get_dataset()` | Dataset metadata |
| POST | `/api/v1/jobs` | 🔒 | `create_job()` | Ask a question → start the agent |
| GET | `/api/v1/jobs/{job_id}/status` | 🔒 | `job_status()` | Poll progress |
| GET | `/api/v1/reports/{report_id}` | 🔒 | `get_report()` | Fetch the finished report |
| GET | `/api/v1/reports` | 🔒 | `list_reports()` | List recent reports |
| POST | `/api/v1/feedback/{report_id}` | 🔒 | `submit_feedback()` | Rate a report |

### The typical sequence
```
POST /datasets            → dataset_id
POST /jobs                → job_id           (status QUEUED, Celery task queued)
GET  /jobs/{job_id}/status  … repeat every few seconds …
                          → status RUNNING, current_node = "code_writer" …
                          → status COMPLETED, report_id
GET  /reports/{report_id} → full report
POST /feedback/{report_id}?rating=5
```

---

## 3. Routes in detail

### 3.1 `GET /` — root

**Input:** none
**Output `200`:**
```json
{"status": "ok", "version": "0.1.0"}
```
**Functions:** `root()` (inner function in `create_app()`), version from `Settings.app_version`.

---

### 3.2 `GET /api/v1/health` — liveness

**Input:** none
**Output `200`:** `{"status": "ok"}`
**Functions:** `health()`. Doesn't touch the DB, so it only shows the process is up. The Docker healthcheck calls this.

---

### 3.3 `GET /api/v1/health/ready` — readiness

**Input:** none
**Output `200`:** `{"status": "ready", "db": "ok"}`
**Output `503`:** `{"detail": "DB not ready: <error>"}`
**Functions:** `readiness()` → runs `SELECT 1` through `get_db()` → `async_session_factory` (`app/db/session.py`).

---

### 3.4 `POST /api/v1/datasets` 🔒 — upload a CSV

**Input:** `multipart/form-data` with one field **`file`** (the CSV).

```bash
curl -X POST http://localhost:8000/api/v1/datasets \
  -H "X-API-Key: dev-key-1" \
  -F "file=@sales.csv"
```

**Output `201`:**
```json
{
  "dataset_id": "3f0c1b8e-6a1d-4c1f-9a77-2b7f0d1e9c42",
  "filename": "sales.csv",
  "status": "READY"
}
```

**What happens / functions:**
1. `upload_dataset()` generates `dataset_id = uuid4()`.
2. Writes the bytes to `data/uploads/<dataset_id>.csv`.
3. Inserts a `Dataset` row (`app/db/base.py`): `filename`, `s3_path` (currently the local path), `size_bytes`, `status="READY"`.
4. `get_db()` commits.

Notes: the file type and size aren't checked yet. `row_count`/`col_count` stay `0`, because the CSV is only parsed later by `data_profiler_node`.

---

### 3.5 `GET /api/v1/datasets/{dataset_id}` 🔒 — dataset metadata

**Input:** path param `dataset_id`.
```bash
curl http://localhost:8000/api/v1/datasets/3f0c1b8e-... -H "X-API-Key: dev-key-1"
```
**Output `200`:**
```json
{
  "dataset_id": "3f0c1b8e-6a1d-4c1f-9a77-2b7f0d1e9c42",
  "filename": "sales.csv",
  "status": "READY",
  "size_bytes": 48213
}
```
**Output `404`:** `{"detail": "Dataset not found"}`
**Functions:** `get_dataset()` → `db.get(Dataset, id)`.

---

### 3.6 `POST /api/v1/jobs` 🔒 — start an analysis  ⭐ the important one

**Input (JSON body)** — schema `JobCreateRequest` (`app/schemas/job.py`):

| Field | Type | Rules | Default |
|---|---|---|---|
| `dataset_id` | string | must exist | required |
| `query` | string | 10–2000 chars | required |
| `config.max_charts` | int | 1–10 | 3 *(not used yet)* |
| `config.output_format` | string | `json`, `html` or `pdf` | `json` *(not used yet)* |
| `config.llm_temperature` | float | 0.0–1.0 | 0.2 *(not used yet)* |
| `config.max_retries` | int | 0–3 | 2 — **used** by `validator_node` and `_should_retry` |

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "X-API-Key: dev-key-1" -H "Content-Type: application/json" \
  -d '{
        "dataset_id": "3f0c1b8e-6a1d-4c1f-9a77-2b7f0d1e9c42",
        "query": "Which product category generated the most revenue in 2024 and how did it trend by month?",
        "config": {"max_retries": 2}
      }'
```

**Output `202 Accepted`** — schema `JobCreateResponse`:
```json
{
  "job_id": "a91e2c55-0d3b-4e8e-8f61-5c1d2b7a9e10",
  "status": "QUEUED",
  "estimated_duration_secs": 45
}
```
**Output `404`:** `{"detail": "Dataset not found"}`
**Output `422`:** e.g. query shorter than 10 chars.

**What happens / functions:**
1. `create_job()` checks the `Dataset` exists.
2. Inserts a `Job` row with `status="QUEUED"` and `config_json`.
3. Calls `run_agent_pipeline.apply_async(args=[dataset_id, query, config], task_id=job_id)`, which puts a message on Redis. **The Celery task id is the job id.**
4. Returns immediately. No LLM work happens in the HTTP request. See `docs/CELERY_GUIDE.md`.

**What runs afterwards in the worker** (`app/workers/pipeline_task.py` → `app/pipeline/graph.py`):

| # | Node function | Output written to state | LLM |
|---|---|---|---|
| 1 | `data_profiler_node` | `data_profile`, `dataset_sample`, `csv_path` | – (pandas) |
| 2 | `goal_parser_node` | `analysis_goal` | GPT-4o-mini |
| 3 | `rag_retriever_node` | `rag_chunks`, `rag_query` | – (Chroma) |
| 4 | `analysis_planner_node` | `analysis_plan` | GPT-4o |
| 5 | `code_writer_node` | `generated_code`, `code_version` | GPT-4o |
| 6 | `code_executor_node` → `run_sandboxed_code()` | `execution_result` | – (subprocess) |
| 7 | `self_critic_node` | `critic_score`, `critic_verdict`, `critic_issues` | GPT-4o-mini |
| 8 | `validator_node` | `should_retry`, `retry_count` (may loop back to 5) | – |
| 9 | `narrative_writer_node` | `synthesis` | Claude Sonnet |
| 10 | `assembler_node` | `final_report` | – |
| 11 | `rag_feedback_writer_node` | – (writes to Chroma) | – |

Then `_store_report()` saves `final_report` into the `reports` table, and `_update_job_status()` sets `COMPLETED` + `report_id`.

---

### 3.7 `GET /api/v1/jobs/{job_id}/status` 🔒 — poll progress

**Input:** path param `job_id`.
```bash
curl http://localhost:8000/api/v1/jobs/a91e2c55-.../status -H "X-API-Key: dev-key-1"
```

**Output `200`** — schema `JobStatusResponse`. Examples at different moments:

Just queued (worker hasn't picked it up):
```json
{"job_id": "a91e2c55-...", "status": "QUEUED", "progress_pct": null, "current_node": null,
 "report_id": null, "error_message": null,
 "created_at": "2026-11-18T10:00:00Z", "updated_at": "2026-11-18T10:00:00Z"}
```
Running (`current_node` changes as each node starts):
```json
{"job_id": "a91e2c55-...", "status": "RUNNING", "progress_pct": null, "current_node": "code_executor",
 "report_id": null, "error_message": null,
 "created_at": "2026-11-18T10:00:00Z", "updated_at": "2026-11-18T10:00:21Z"}
```
Finished:
```json
{"job_id": "a91e2c55-...", "status": "COMPLETED", "progress_pct": null, "current_node": "rag_feedback_writer",
 "report_id": "7d4b9a10-2c3e-4f5a-8b6c-1d2e3f4a5b6c", "error_message": null,
 "created_at": "2026-11-18T10:00:00Z", "updated_at": "2026-11-18T10:00:44Z"}
```
Failed (`current_node` = the node that crashed):
```json
{"job_id": "a91e2c55-...", "status": "FAILED", "progress_pct": null, "current_node": "goal_parser",
 "report_id": null, "error_message": "Error code: 401 - Incorrect API key provided",
 "created_at": "...", "updated_at": "..."}
```
**Output `404`:** `{"detail": "Job not found"}`

**Functions:** `job_status()` reads the `Job` row. The row is written by the worker:
- `run_agent_pipeline()` → `_on_node_start()` → `_update_job_status(job_id, "RUNNING", current_node=...)` for every node (via `_run_graph()`).
- `_update_job_status(..., "COMPLETED", report_id=...)` at the end, or `"FAILED", error=...` on an exception or timeout.

`progress_pct` is in the schema but nothing fills it yet.

---

### 3.8 `GET /api/v1/reports/{report_id}` 🔒 — the finished report

**Input:** path param `report_id` (from the job status).
```bash
curl http://localhost:8000/api/v1/reports/7d4b9a10-... -H "X-API-Key: dev-key-1"
```

**Output `200`:**
```json
{
  "report_id": "7d4b9a10-2c3e-4f5a-8b6c-1d2e3f4a5b6c",
  "job_id": "a91e2c55-0d3b-4e8e-8f61-5c1d2b7a9e10",
  "dataset_id": "3f0c1b8e-6a1d-4c1f-9a77-2b7f0d1e9c42",
  "report": {
    "report_id": "7d4b9a10-2c3e-4f5a-8b6c-1d2e3f4a5b6c",
    "job_id": "a91e2c55-0d3b-4e8e-8f61-5c1d2b7a9e10",
    "dataset_id": "3f0c1b8e-6a1d-4c1f-9a77-2b7f0d1e9c42",
    "query": "Which product category generated the most revenue in 2024 and how did it trend by month?",
    "summary": "Electronics led 2024 revenue with $1.42M (38% of total), peaking in November ...",
    "insights": [
      {
        "insight_id": "ins_1",
        "title": "Electronics dominates revenue",
        "body": "Electronics contributed $1.42M of $3.74M total revenue (38.0%) ...",
        "confidence": 0.9,
        "supporting_data": {"electronics_revenue": 1420000, "share": 0.38}
      }
    ],
    "charts": [
      {
        "chart_id": "a1b2c3d4",
        "title": "Chart 1",
        "chart_type": "bar",
        "x_col": null, "y_col": null, "color_col": null,
        "s3_url": "/tmp/charts/revenue_by_category.png",
        "description": ""
      }
    ],
    "raw_code": "monthly = df.groupby(['month','category'])['revenue'].sum() ...",
    "rag_context_used": ["Query: ... Summary: ..."],
    "model_versions": {"planner": "gpt-4o", "narrative": "claude-sonnet-4-6"},
    "created_at": "2026-11-18T10:00:43.512Z",
    "quality_score": null
  }
}
```
**Output `404`:** `{"detail": "Report not found"}`

**Which function builds each part of `report`:**

| Field | Built by | From |
|---|---|---|
| `report_id`, `created_at` | `assembler_node` | new uuid / now (the DB row uses the same id, via `_store_report`) |
| `job_id`, `dataset_id`, `query` | `assembler_node` | initial state |
| `summary`, `insights[]` | `narrative_writer_node` (Claude) → `assembler_node` makes `InsightBlock`s | `synthesis` |
| `charts[]` | `run_sandboxed_code()` finds new PNGs → `assembler_node` makes `ChartSpec`s | `execution_result.charts_generated` |
| `raw_code` | `code_writer_node` | `generated_code` |
| `rag_context_used` | `rag_retriever_node` | `rag_chunks` |
| `model_versions` | `assembler_node` | hard-coded |
| `quality_score` | nothing yet | always `null` |

If code execution fails after all retries, the graph jumps straight to `assembler_node` (the `"fail"` edge). The report then has an empty `summary` and no `insights`, but `raw_code` is still filled in.

---

### 3.9 `GET /api/v1/reports` 🔒 — list reports

**Input:** query params `limit` (default 10), `offset` (default 0).
```bash
curl "http://localhost:8000/api/v1/reports?limit=5&offset=0" -H "X-API-Key: dev-key-1"
```
**Output `200`:**
```json
{
  "reports": [
    {"report_id": "7d4b9a10-...", "job_id": "a91e2c55-..."},
    {"report_id": "5c2e8f31-...", "job_id": "e0b7d6a2-..."}
  ],
  "total": 2,
  "limit": 5,
  "offset": 0
}
```
**Functions:** `list_reports()` → `select(Report).order_by(created_at desc).limit().offset()`. `total` is the number of rows in *this page*, not the overall count.

---

### 3.10 `POST /api/v1/feedback/{report_id}` 🔒 — rate a report

**Input:** path `report_id`, **query params** (not JSON body) `rating` (int, required) and `comment` (string, optional).
```bash
curl -X POST "http://localhost:8000/api/v1/feedback/7d4b9a10-...?rating=5&comment=great" \
  -H "X-API-Key: dev-key-1"
```
**Output `200`:**
```json
{"feedback_id": "1", "report_id": "7d4b9a10-...", "accepted": true}
```
**Output `404`:** `{"detail": "Report not found"}`
**Functions:** `submit_feedback()` inserts a `Feedback` row. `rating` has no range check yet.

---

## 4. Python client example (end to end)

```python
import time, requests

BASE = "http://localhost:8000/api/v1"
H = {"X-API-Key": "dev-key-1"}

ds = requests.post(f"{BASE}/datasets", headers=H, files={"file": open("sales.csv", "rb")}).json()
job = requests.post(f"{BASE}/jobs", headers=H, json={
    "dataset_id": ds["dataset_id"],
    "query": "Which product category generated the most revenue in 2024?",
}).json()

while True:
    st = requests.get(f"{BASE}/jobs/{job['job_id']}/status", headers=H).json()
    print(st["status"], st["current_node"])
    if st["status"] in ("COMPLETED", "FAILED"):
        break
    time.sleep(3)

if st["status"] == "COMPLETED":
    report = requests.get(f"{BASE}/reports/{st['report_id']}", headers=H).json()["report"]
    print(report["summary"])
    for ins in report["insights"]:
        print("-", ins["title"], ":", ins["body"])
else:
    print("Failed:", st["error_message"])
```
