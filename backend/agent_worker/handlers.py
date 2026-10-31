"""
Job handlers for the OpenCode worker.

Register a handler with `@handler("job_type")`. The function receives the open
session and the claimed job row (id, tenant_id, job_type, payload, attempts,
max_attempts) and returns JSON-serialisable data that is stored in
`agent_jobs.result`.

Rules:
- Always scope reads and writes by `job["tenant_id"]`. Clients must never see
  each other's data.
- Raise to fail the job. The worker retries with backoff, then marks it failed
  and records the error on the row.
- Keep handlers idempotent where possible: a retry re-runs the handler.
"""
from __future__ import annotations

import platform
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

Handler = Callable[[AsyncSession, dict], Awaitable[Any]]

HANDLERS: dict[str, Handler] = {}


def handler(job_type: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        if job_type in HANDLERS:
            raise ValueError(f"handler already registered for '{job_type}'")
        HANDLERS[job_type] = fn
        return fn

    return register


# ── Health check ─────────────────────────────────────────────────────────────
@handler("ping")
async def ping(_db: AsyncSession, job: dict) -> dict:
    """Smoke test: proves the queue, the claim and the result write all work."""
    return {
        "pong": True,
        "job_id": str(job["id"]),
        "tenant_id": str(job["tenant_id"]) if job["tenant_id"] else None,
        "payload": job.get("payload"),
        "host": platform.node(),
        "handled_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Business jobs (not implemented yet) ──────────────────────────────────────
# Each of these is the place to write the real script. They raise on purpose so
# the job shows as failed in the dashboard instead of silently doing nothing.
@handler("lead_generation")
async def lead_generation(_db: AsyncSession, job: dict) -> dict:
    raise NotImplementedError(
        "lead_generation handler is not implemented yet. "
        "Write the scraper/enrichment script here and return the created leads."
    )


@handler("social_media")
async def social_media(_db: AsyncSession, job: dict) -> dict:
    raise NotImplementedError(
        "social_media handler is not implemented yet. "
        "Write the scheduling/publishing script here and return what was published."
    )
