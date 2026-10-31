# OpenCode Worker — execution engine

Polls the `agent_jobs` table and runs the handler registered for each job type.
Jobs are enqueued by the dashboard (`job_type`, `tenant_id`, `payload`) and the
worker writes back `status`, `result` or `error`.

## Run

```bash
cd backend/agent_worker
pip install -r requirements.txt
export DATABASE_URL="postgresql+asyncpg://postgres:localpass@localhost:5433/ffinn"
python worker.py
```

Against the Docker stack, run it inside the API container so it shares the
database network:

```bash
docker compose cp backend/agent_worker api:/tmp/agent_worker
docker compose exec -e DATABASE_URL="postgresql+asyncpg://postgres:localpass@db:5432/ffinn" \
  api sh -c "cd /tmp/agent_worker && python worker.py"
```

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | — (required) | Async SQLAlchemy URL |
| `WORKER_ID` | `<hostname>-<pid>` | Written to `agent_jobs.worker_id` |
| `POLL_INTERVAL` | `5` | Seconds to wait when the queue is empty |
| `JOB_MAX_ATTEMPTS` | `3` | Fallback retry cap when the row has none |
| `WORKER_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Job lifecycle

`queued` → `running` → `succeeded` | `failed`

On failure the worker retries with exponential backoff (60 s, 2 m, 4 m … capped
at 15 m) until `max_attempts`, then marks the row `failed` and stores the error.
Claims use `FOR UPDATE SKIP LOCKED`, so running several worker processes is safe.

## Adding a job type

Add a handler in `handlers.py`:

```python
@handler("seo_audit")
async def seo_audit(db, job):
    ...
    return {"summary": ..., "artifacts": [...]}
```

Everything returned is stored in `agent_jobs.result` as JSON. Scope every query
by `job["tenant_id"]` — multi-tenant isolation is not optional.

Registered today: `ping` (health check), `lead_generation` and `social_media`
(explicit `NotImplementedError` placeholders — write the real scripts there).
