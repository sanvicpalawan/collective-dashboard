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

import asyncio
import platform
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scraper import find_leads

Handler = Callable[[AsyncSession, dict], Awaitable[Any]]

HANDLERS: dict[str, Handler] = {}

# How many real businesses one search may return.
LEAD_RESULT_LIMIT = 10


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


# ── Lead generation ──────────────────────────────────────────────────────────
# Real data, two free sources: OpenStreetMap (Nominatim + Overpass) for
# structured business records, DuckDuckGo HTML to find each business's own
# website and read a `mailto:` out of it. See scraper.py for the why and the
# request budget.
INSERT_LEAD_SQL = text(
    """
    INSERT INTO leads (
        id, tenant_id, business_name, email, phone, website, status,
        niche, location, source, job_id
    )
    SELECT
        :id, :tenant_id, :business_name, :email, :phone, :website, 'new',
        :niche, :location, :source, :job_id
    WHERE NOT EXISTS (
        -- Re-running a search must not duplicate rows. NULL tenant_id (host
        -- workspace) never conflicts in a unique index, and phone-only leads
        -- have a NULL email, so the dedupe is explicit.
        SELECT 1 FROM leads
        WHERE tenant_id IS NOT DISTINCT FROM :tenant_id
          AND (
            (email IS NOT NULL AND email = CAST(:email AS varchar(320)))
            OR business_name = CAST(:business_name AS varchar(256))
          )
    )
    ON CONFLICT (tenant_id, email) DO NOTHING
    RETURNING id
    """
)


@handler("lead_generation")
async def lead_generation(db: AsyncSession, job: dict) -> dict:
    """
    Find real businesses for `{"niche": "...", "location": "..."}` and store them.

    Results land in `leads`, scoped to the job's tenant. A search that finds
    nothing is not an error: it completes with `created: 0` and notes explaining
    which sources were tried.
    """
    # None is the host workspace (a platform admin with no tenant); it is still a
    # scope of its own — no tenant user can ever read those rows.
    tenant_id = job["tenant_id"]

    payload = job.get("payload") or {}
    niche = str(payload.get("niche") or "").strip()
    location = str(payload.get("location") or "").strip()
    if not niche or not location:
        raise ValueError("payload must include non-empty 'niche' and 'location'")

    # Scraping is blocking I/O (requests); keep it off the worker's event loop.
    report = await asyncio.to_thread(find_leads, niche, location, LEAD_RESULT_LIMIT)

    created: list[dict] = []
    for lead in report.leads:
        row = await db.execute(
            INSERT_LEAD_SQL,
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "business_name": lead.business_name[:256],
                "email": lead.email,
                "phone": lead.phone,
                "website": lead.website,
                "niche": niche,
                "location": location,
                "source": lead.source,
                "job_id": job["id"],
            },
        )
        new_id = row.scalar()
        if new_id is not None:
            created.append(
                {
                    "id": str(new_id),
                    "business_name": lead.business_name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "website": lead.website,
                    "source": lead.source,
                }
            )

    await db.commit()

    return {
        "mock": False,
        "niche": niche,
        "location": location,
        "requested": LEAD_RESULT_LIMIT,
        "found": len(report.leads),
        "created": len(created),
        "skipped": len(report.leads) - len(created),
        "notes": report.notes,
        "leads": created,
    }


# ── Business jobs (not implemented yet) ──────────────────────────────────────
@handler("social_media")
async def social_media(_db: AsyncSession, job: dict) -> dict:
    raise NotImplementedError(
        "social_media handler is not implemented yet. "
        "Write the scheduling/publishing script here and return what was published."
    )
