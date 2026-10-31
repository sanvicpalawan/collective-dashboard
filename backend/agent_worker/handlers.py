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

import hashlib
import platform
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import text
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


# ── Lead generation ──────────────────────────────────────────────────────────
# The real tool will call an outbound source (Maps/Places style API, directory
# scrape). Until that integration exists, the handler produces a deterministic
# mock set so the whole pipeline — queue, worker, table, UI — is exercised and
# every run is reproducible and obviously synthetic (`.example.com` addresses).
MOCK_PREFIXES = ("Bayview", "Harbour", "Sunset", "Coral", "Highland")
MOCK_LEAD_COUNT = 5


def _singular(word: str) -> str:
    """Crude singulariser so 'dentists' → 'Dentist' in a business name."""
    w = word.strip()
    low = w.lower()
    if low.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if low.endswith(("ss", "ses", "us", "is")):
        return w
    if low.endswith("s") and len(w) > 3:
        return w[:-1]
    return w


def _digits(seed: str, count: int) -> str:
    """Deterministic pseudo-random digits, so a rerun yields the same phone."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return "".join(c for c in digest if c.isdigit())[:count].ljust(count, "7")


def build_mock_leads(niche: str, location: str, count: int = MOCK_LEAD_COUNT) -> list[dict]:
    noun = _singular(niche).title()
    leads: list[dict] = []
    for i in range(count):
        name = f"{MOCK_PREFIXES[i % len(MOCK_PREFIXES)]} {noun} {location}"
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        d = _digits(f"{niche.lower()}|{location.lower()}|{i}", 9)
        leads.append(
            {
                "business_name": name[:256],
                # Reserved documentation domain — these addresses never exist.
                "email": f"hello@{slug[:180]}.example.com",
                "phone": f"+63 9{d[0]}{d[1]} {d[2]}{d[3]}{d[4]} {d[5]}{d[6]}{d[7]}{d[8]}",
            }
        )
    return leads


INSERT_LEAD_SQL = text(
    """
    INSERT INTO leads (
        id, tenant_id, business_name, email, phone, status, niche, location, source, job_id
    )
    SELECT
        :id, :tenant_id, :business_name, :email, :phone, 'new', :niche, :location, :source, :job_id
    WHERE NOT EXISTS (
        -- NULL tenant_id (host workspace) never conflicts in a unique index, so
        -- the dedupe is explicit. IS NOT DISTINCT FROM covers both cases.
        SELECT 1 FROM leads
        WHERE tenant_id IS NOT DISTINCT FROM :tenant_id
          AND email = CAST(:email AS varchar(320))
    )
    ON CONFLICT (tenant_id, email) DO NOTHING
    RETURNING id
    """
)


@handler("lead_generation")
async def lead_generation(db: AsyncSession, job: dict) -> dict:
    """
    Find businesses for `{"niche": "...", "location": "..."}` and store them.

    The results land in `leads`, scoped to the job's tenant, so the dashboard can
    list them. Re-running the same search is safe: duplicates are skipped rather
    than inserted twice.
    """
    # None is the host workspace (a platform admin with no tenant); it is still a
    # scope of its own — no tenant user can ever read those rows.
    tenant_id = job["tenant_id"]

    payload = job.get("payload") or {}
    niche = str(payload.get("niche") or "").strip()
    location = str(payload.get("location") or "").strip()
    if not niche or not location:
        raise ValueError("payload must include non-empty 'niche' and 'location'")

    found = build_mock_leads(niche, location)

    created: list[dict] = []
    for lead in found:
        row = await db.execute(
            INSERT_LEAD_SQL,
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "business_name": lead["business_name"],
                "email": lead["email"],
                "phone": lead["phone"],
                "niche": niche,
                "location": location,
                "source": "mock",
                "job_id": job["id"],
            },
        )
        new_id = row.scalar()
        if new_id is not None:
            created.append({"id": str(new_id), **lead})

    await db.commit()

    return {
        "mock": True,
        "niche": niche,
        "location": location,
        "requested": len(found),
        "created": len(created),
        "skipped": len(found) - len(created),
        "leads": created,
    }


# ── Business jobs (not implemented yet) ──────────────────────────────────────
@handler("social_media")
async def social_media(_db: AsyncSession, job: dict) -> dict:
    raise NotImplementedError(
        "social_media handler is not implemented yet. "
        "Write the scheduling/publishing script here and return what was published."
    )
