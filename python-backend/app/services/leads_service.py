from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.agent_job import AgentJob
from app.domain.models.lead import Lead

LEAD_JOB_TYPE = "lead_generation"


class LeadsService:
    """Business logic and DB access for the Lead Generation tool."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_leads(
        self, tenant_id: Optional[uuid.UUID], limit: int = 200, offset: int = 0
    ) -> List[Lead]:
        stmt = (
            select(Lead)
            .where(Lead.tenant_id == tenant_id)
            .order_by(Lead.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def enqueue_search(
        self,
        tenant_id: Optional[uuid.UUID],
        created_by: Optional[uuid.UUID],
        niche: str,
        location: str,
    ) -> AgentJob:
        """Queue a `lead_generation` job. The worker does the actual work."""
        job = AgentJob(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            created_by=created_by,
            job_type=LEAD_JOB_TYPE,
            payload={"niche": niche, "location": location},
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_job(
        self, tenant_id: Optional[uuid.UUID], job_id: uuid.UUID
    ) -> Optional[AgentJob]:
        stmt = select(AgentJob).where(
            AgentJob.id == job_id,
            AgentJob.job_type == LEAD_JOB_TYPE,
            AgentJob.tenant_id == tenant_id,
        )
        return (await self.db.execute(stmt)).scalars().first()
