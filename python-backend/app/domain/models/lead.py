"""
Leads — businesses found by the `lead_generation` job.

The dashboard enqueues a search (niche + location); the worker writes the
results here. Every row is tenant-scoped: `tenant_id` is indexed and every read
must filter on it so one client can never see another client's leads.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.database import Base


class Lead(Base):
    __tablename__ = "leads"
    # A retried job must not duplicate rows: the same business email within a
    # tenant is one lead. The worker inserts with ON CONFLICT DO NOTHING.
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_leads_tenant_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Tenant scope. Every query must filter on this.
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    business_name: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # new | contacted | qualified | won | lost
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="new", server_default="new", index=True
    )

    # Provenance: which search produced the lead and which job ran it.
    niche: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
