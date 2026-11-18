# Celery in AutoInsight — A Beginner's Guide

## 1. Why do we need Celery at all?

One report takes **30–90 seconds**: several LLM calls, running generated code, sometimes retries.
If the API did that inside the HTTP request:
- the client would wait a minute and probably time out,
- each slow request would tie up an API worker,
- a crash halfway through would lose everything with no record.

So the API only **writes down the job and drops it in a queue**. A separate process called the **worker** picks it up and does the slow part. The client polls for the result.

```
          (fast, ~50 ms)                          (slow, ~60 s)
Client ──► API ──► Postgres: jobs row QUEUED
             └──► Redis queue: "run job X" ──────► Celery worker ──► LangGraph pipeline
                                                        │
Client ◄── API ◄── Postgres: jobs row RUNNING/COMPLETED ◄┘ (worker updates the row)
```

---

## 2. The five words you need

| Term | What it means | In this project |
|---|---|---|
| **Task** | A Python function Celery can run in the background | `run_agent_pipeline` in `app/workers/pipeline_task.py` |
| **Broker** | The queue that holds "please run this task" messages | Redis DB 0 (`CELERY_BROKER_URL=redis://localhost:6379/0`) |
| **Worker** | A separate process that takes messages off the broker and runs tasks | `celery -A app.workers.celery_app worker` |
| **Result backend** | Where Celery stores a task's return value | Redis DB 1 (`CELERY_RESULT_BACKEND`). **Our API doesn't read it.** It reads Postgres instead (see §6). |
| **Producer** | Whoever sends the task message | The API's `create_job()` via `apply_async()` |

---

## 3. The two files

### `app/workers/celery_app.py` — the Celery "app"

```python
celery_app = Celery(
    "autoinsight",
    broker=settings.celery_broker_url,        # where to read/write task messages
    backend=settings.celery_result_backend,   # where to store return values
    include=["app.workers.pipeline_task"],    # modules to import so the worker knows our tasks
)
```

Every setting in `celery_app.conf.update(...)`:

| Setting | Value | Why |
|---|---|---|
| `task_serializer` / `result_serializer` / `accept_content` | `json` | Messages are plain JSON. That's safe and readable, but task arguments must be JSON-friendly (str, int, dict, list), so we pass `config.model_dump()` and not the Pydantic object. |
| `task_track_started` | `True` | Celery records a `STARTED` state, not just PENDING → SUCCESS. |
| `task_soft_time_limit` | `240` s | After 4 min, Celery raises `SoftTimeLimitExceeded` *inside* the task. We catch it and mark the job FAILED. |
| `task_time_limit` | `300` s | After 5 min the worker process is **killed**. No Python code runs, so the job row could be left `RUNNING`. The soft limit exists so this rarely happens. |
| `worker_prefetch_multiplier` | `1` | Each worker slot reserves only one job at a time. With long jobs, prefetching would leave jobs waiting behind a busy slot while other slots sit idle. |
| `worker_max_tasks_per_child` | `50` | Restart each worker process after 50 jobs, to free memory that pandas, matplotlib and the LLM SDKs leak. |
| `result_expires` | `86400` | Return values in Redis are deleted after 24 h. |

### `app/workers/pipeline_task.py` — the task

```python
@celery_app.task(bind=True, name="run_agent_pipeline", max_retries=0)
def run_agent_pipeline(self, dataset_id, query, config): ...
```
- `bind=True` → the first argument `self` is the task instance, so we can read `self.request.id`.
- `name="run_agent_pipeline"` → a fixed name, so the producer and worker agree even if the module moves.
- `max_retries=0` → Celery never re-runs the whole pipeline. Retries happen at a finer level: tenacity retries each LLM call 3×, and the graph's critic loop re-writes code.

---

## 4. Life of one job, step by step

### Step 1 — the API sends the task (`app/api/routes.py` → `create_job()`)
```python
job = Job(job_id=job_id, ..., status="QUEUED")
db.add(job); await db.flush()

from app.workers.pipeline_task import run_agent_pipeline
run_agent_pipeline.apply_async(
    args=[request.dataset_id, request.query, request.config.model_dump()],
    task_id=job_id,               # ← key trick
)
return JobCreateResponse(job_id=job_id, status="QUEUED")
```
- `apply_async(...)` **does not run the function**. It serializes the arguments to JSON and pushes a message to Redis, then returns in milliseconds.
- `task_id=job_id` makes the Celery task id **equal** the Postgres job id, so the worker knows which `jobs` row to update without passing the id separately.
- The import sits inside the function so the API only loads Celery when it actually needs to send a task.

### Step 2 — the worker picks it up
The worker process (started with `celery -A app.workers.celery_app worker ...`) is always listening on Redis. When the message arrives it calls `run_agent_pipeline(dataset_id, query, config)` in one of its pool processes.

### Step 3 — the task runs the agent
```python
job_id = self.request.id                       # == the Postgres job id
_update_job_status(job_id, "RUNNING", current_node="data_profiler")

graph = build_graph()
final_state = _run_graph(graph, initial_state, on_node_start=_on_node_start)
#   └─ every time a node starts → _update_job_status(job_id, "RUNNING", current_node=<node>)

report_id = asyncio.run(_store_report(job_id, dataset_id, final_state["final_report"]))
_update_job_status(job_id, "COMPLETED", report_id=report_id)
return {"status": "COMPLETED", "report_id": report_id}   # → stored in result backend
```

### Step 4 — failure handling
```python
except SoftTimeLimitExceeded:  → job FAILED, "Pipeline timed out"
except Exception as exc:       → job FAILED, error_message = str(exc)
```
Both re-`raise`, so Celery also marks the task as FAILURE (visible in logs and Flower). `current_node` keeps the name of the node that was running when it failed, which is handy for debugging.

### Step 5 — the client polls
`GET /jobs/{job_id}/status` → `job_status()` reads the `jobs` row the worker has been updating.

```
QUEUED ──(worker picks up)──► RUNNING (current_node changes 11+ times) ──► COMPLETED
                                         └──(exception / soft timeout)──► FAILED
```

---

## 5. Why `asyncio.run(...)` and `NullPool` in the worker?

- The database layer uses **async** SQLAlchemy (asyncpg), because FastAPI is async.
- Celery tasks are **plain sync functions**.
- To call async code from sync code we use `asyncio.run(coro)`, which creates a fresh event loop, runs the coroutine and closes the loop.

Database connections belong to the event loop that opened them. If we used the API's pooled engine, a connection created in one `asyncio.run` would be reused in the next, which is a different, closed loop, and you'd get errors like *"attached to a different loop"*. So `_async_update_job()` and `_store_report()`:
1. create a throwaway engine with `poolclass=NullPool` (no connection reuse),
2. do their one update,
3. call `engine.dispose()`.

That costs a little per update, which is fine at ~15 updates per job.

---

## 6. Why does the API read Postgres instead of the Celery result backend?

Celery can tell you a task's state (`AsyncResult(job_id).state`). We use Postgres instead because:
- Postgres is permanent, while Redis results expire after 24 h.
- We store more than Celery does: `current_node`, `error_message`, `report_id`, timestamps.
- The API needs to answer "list my reports" and similar queries, which need SQL anyway.

The result backend is still configured. It holds `{"status": "COMPLETED", "report_id": ...}` and is useful for debugging or Flower.

---

## 7. Running it

### With Docker (easiest — runs everything)
```bash
docker-compose up --build
```
The `worker` service runs `celery -A app.workers.celery_app worker --loglevel=info --concurrency=4`. It shares `./data` (uploads) and `/tmp/charts` with the host.

Watch only the worker's logs:
```bash
docker-compose logs -f worker
```

### Locally without Docker
Start Redis and Postgres (`make redis`, `make db`, `make migrate`), then in two terminals:
```bash
make dev
```
```bash
make worker
```

**On Windows**, Celery's default `prefork` pool isn't supported. Use the solo pool, which runs one job at a time:
```bash
celery -A app.workers.celery_app worker --loglevel=info --pool=solo
```

### Command flags explained
| Flag | Meaning |
|---|---|
| `-A app.workers.celery_app` | Python path to the module containing `celery_app` |
| `worker` | Start a worker (other subcommands: `inspect`, `purge`, `flower`…) |
| `--loglevel=info` | Show each task received / succeeded / failed |
| `--concurrency=4` | 4 child processes means 4 jobs in parallel |
| `--pool=solo` | No child processes. Needed on Windows, handy for debugging. |

---

## 8. Debugging and inspecting

**Run the task without a worker** (synchronously, in your shell). This is great for stepping through with a debugger:
```python
from app.workers.pipeline_task import run_agent_pipeline
run_agent_pipeline.apply(args=["<dataset_id>", "Which category earned the most?", {"max_retries": 2}],
                         task_id="<existing job_id>")
```
`.apply()` runs in-process, while `.apply_async()` sends to the queue.

**Run only the graph** (no Celery, no DB):
```python
from app.pipeline.graph import build_graph
build_graph().invoke({"job_id": "local", "dataset_id": "demo", "query": "...", "config": {}})
```

**Ask the running workers what they're doing:**
```bash
celery -A app.workers.celery_app inspect active
```
```bash
celery -A app.workers.celery_app inspect registered
```

**Check a task's Celery-side state:**
```python
from app.workers.celery_app import celery_app
r = celery_app.AsyncResult("<job_id>")
r.state, r.result
```

**Empty the queue** (deletes all waiting jobs):
```bash
celery -A app.workers.celery_app purge
```

**Web dashboard:** Flower is commented out in `requirements.txt`. To try it:
```bash
pip install flower
```
```bash
celery -A app.workers.celery_app flower --port=5555
```

---

## 9. Common problems

| Symptom | Likely cause | Fix |
|---|---|---|
| Job stays **QUEUED** forever | No worker running, or the worker points at a different Redis | Start the worker and check `CELERY_BROKER_URL` is the same for API and worker |
| Worker log shows `Received unregistered task 'run_agent_pipeline'` | Worker started without the right `-A`, or `include=` is missing the module | Use `-A app.workers.celery_app` |
| Job stuck in **RUNNING** with no change | Hard time limit (300 s) killed the process before it could write FAILED, or the worker crashed | Check worker logs. Lower the sandbox timeout or LLM token limits. |
| `FileNotFoundError: data/uploads/<id>.csv` | Worker can't see the files the API saved (different machine or container) | Share the `./data` volume (compose already does). Long-term: S3. |
| `... attached to a different loop` | Reusing a pooled async engine across `asyncio.run` calls | Keep the `NullPool` + `dispose()` pattern from §5 |
| Prompt edits have no effect | Prompts load once at import time | Restart the worker |
| Windows: `ValueError: not enough values to unpack` or the worker hangs | `prefork` pool on Windows | Add `--pool=solo` |

---

## 10. Cheat sheet

```
API side                                       Worker side
────────                                       ───────────
create_job()                                   run_agent_pipeline(self, dataset_id, query, config)
  Job(status=QUEUED)                             job_id = self.request.id
  run_agent_pipeline.apply_async(                _update_job_status(RUNNING)
      args=[...], task_id=job_id) ──Redis──►     _run_graph(...)  → current_node per node
  return 202 {job_id}                            _store_report(...)
                                                 _update_job_status(COMPLETED, report_id)
job_status()  ◄────────── Postgres jobs row ─────┘
```
