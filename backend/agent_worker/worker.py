#!/usr/bin/env python3
"""
OpenCode worker — the execution engine for the AI Agency OS.

Polls the `agent_jobs` table, claims one job at a time with
`FOR UPDATE SKIP LOCKED`, runs the handler registered for that job type, and
writes the result (or the failure) back to the row.

Run it:
    python backend/agent_worker/worker.py

Environment:
    DATABASE_URL        postgresql+asyncpg://user:pass@host:5432/db   (required)
    WORKER_ID           defaults to "<hostname>-<pid>"
    POLL_INTERVAL       seconds to wait when the queue is empty (default 5)
    JOB_MAX_ATTEMPTS    default cap when the row has none (default 3)
    WORKER_LOG_LEVEL    default INFO

Design notes:
- One job at a time per process. Start more processes to scale out; the
  SKIP LOCKED claim makes that safe.
- Every claim, result and failure is written to the row, so the dashboard can
  show job state without reading worker logs.
- A handler that raises marks the job failed. Long jobs are not killed: the row
  keeps its `started_at` so a stuck job can be spotted and reset.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import sys
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from handlers import HANDLERS

# ── Config ────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
WORKER_ID = os.environ.get("WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "5"))
JOB_MAX_ATTEMPTS = int(os.environ.get("JOB_MAX_ATTEMPTS", "3"))
LOG_LEVEL = os.environ.get("WORKER_LOG_LEVEL", "INFO").upper()

Handler = Callable[[AsyncSession, dict], Awaitable[Any]]


# ── Logging ───────────────────────────────────────────────────────────────────
def log(level: str, message: str, **fields: Any) -> None:
    """Plain, greppable logs. Swap for structlog JSON if shipping to a log store."""
    order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
    if order.get(level, 20) < order.get(LOG_LEVEL, 20):
        return
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"{stamp} {level:<7} [{WORKER_ID}] {message}{(' ' + extra) if extra else ''}", flush=True)


# ── Claim query ───────────────────────────────────────────────────────────────
CLAIM_SQL = text(
    """
    WITH next_job AS (
        SELECT id
        FROM agent_jobs
        WHERE status = 'queued'
          AND (run_after IS NULL OR run_after <= now())
        ORDER BY priority DESC, created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    UPDATE agent_jobs j
    SET status = 'running',
        started_at = now(),
        updated_at = now(),
        attempts = j.attempts + 1,
        worker_id = :worker_id
    FROM next_job
    WHERE j.id = next_job.id
    RETURNING j.id, j.tenant_id, j.job_type, j.payload, j.attempts, j.max_attempts
    """
)


async def claim_job(db: AsyncSession) -> Optional[dict]:
    result = await db.execute(CLAIM_SQL, {"worker_id": WORKER_ID})
    row = result.mappings().first()
    if not row:
        return None
    job = dict(row)
    # asyncpg returns JSON as text through a plain text() query; handlers expect a dict.
    if isinstance(job.get("payload"), str):
        try:
            job["payload"] = json.loads(job["payload"])
        except json.JSONDecodeError:
            pass
    return job


SUCCESS_SQL = text(
    """
    UPDATE agent_jobs
    SET status = 'succeeded', result = CAST(:result AS JSONB), error = NULL,
        completed_at = now(), updated_at = now()
    WHERE id = :id
    """
)

RETRY_SQL = text(
    """
    UPDATE agent_jobs
    SET status = 'queued', error = :error, run_after = :run_after,
        completed_at = NULL, updated_at = now()
    WHERE id = :id
    """
)

FAIL_SQL = text(
    """
    UPDATE agent_jobs
    SET status = 'failed', error = :error, completed_at = now(), updated_at = now()
    WHERE id = :id
    """
)


# ── Execution ─────────────────────────────────────────────────────────────────
async def run_job(db: AsyncSession, job: dict) -> None:
    job_type = job["job_type"]
    handler: Optional[Handler] = HANDLERS.get(job_type)
    log("INFO", "claimed", job_id=str(job["id"]), job_type=job_type, tenant_id=str(job["tenant_id"]),
        attempt=f"{job['attempts']}/{job['max_attempts']}")

    if handler is None:
        message = f"No handler registered for job_type '{job_type}'. Known: {sorted(HANDLERS)}"
        log("ERROR", "unhandled", job_id=str(job["id"]), job_type=job_type)
        await db.execute(FAIL_SQL, {"id": job["id"], "error": message})
        await db.commit()
        return

    started = datetime.now(timezone.utc)
    try:
        result = await handler(db, job)
        await db.execute(SUCCESS_SQL, {"id": job["id"], "result": json.dumps(result, default=str)})
        await db.commit()
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        log("INFO", "succeeded", job_id=str(job["id"]), job_type=job_type, seconds=round(elapsed, 2))

    except Exception as exc:  # noqa: BLE001 — one bad job must not kill the worker
        await db.rollback()
        error = f"{exc.__class__.__name__}: {exc}"
        attempts = job["attempts"]
        max_attempts = job["max_attempts"] or JOB_MAX_ATTEMPTS

        if attempts < max_attempts:
            backoff = min(60 * (2 ** (attempts - 1)), 900)  # 60s, 2m, 4m … capped at 15m
            run_after = datetime.now(timezone.utc) + timedelta(seconds=backoff)
            await db.execute(RETRY_SQL, {"id": job["id"], "error": error, "run_after": run_after})
            log("WARNING", "retry", job_id=str(job["id"]), job_type=job_type,
                attempt=f"{attempts}/{max_attempts}", backoff=f"{backoff}s", error=error)
        else:
            await db.execute(FAIL_SQL, {"id": job["id"], "error": error})
            log("ERROR", "failed", job_id=str(job["id"]), job_type=job_type, error=error)
        await db.commit()
        log("DEBUG", "traceback", detail=traceback.format_exc(limit=3).replace("\n", " | "))


# ── Loop ──────────────────────────────────────────────────────────────────────
async def main() -> int:
    if not DATABASE_URL:
        log("ERROR", "DATABASE_URL is not set")
        return 2
    if not HANDLERS:
        log("WARNING", "no handlers registered — every job will fail")

    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_size=2, max_overflow=2)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stop = asyncio.Event()

    def _request_stop(*_: Any) -> None:
        log("INFO", "shutdown requested")
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _request_stop)
        except (ValueError, AttributeError):
            pass  # not available on every platform

    log("INFO", "worker started", handlers=",".join(sorted(HANDLERS)) or "none", poll_interval=POLL_INTERVAL)

    # Fail loudly if the queue table is missing rather than looping forever.
    try:
        async with session_factory() as db:
            await db.execute(text("SELECT 1 FROM agent_jobs LIMIT 1"))
    except Exception as exc:  # noqa: BLE001
        log("ERROR", "agent_jobs table not reachable — run `alembic upgrade head`", error=str(exc))
        await engine.dispose()
        return 3

    try:
        while not stop.is_set():
            async with session_factory() as db:
                try:
                    job = await claim_job(db)
                    await db.commit()
                except Exception as exc:  # noqa: BLE001
                    await db.rollback()
                    log("ERROR", "claim failed", error=str(exc))
                    job = None

                if job:
                    await run_job(db, job)
                    continue

            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass
    finally:
        await engine.dispose()
        log("INFO", "worker stopped")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
