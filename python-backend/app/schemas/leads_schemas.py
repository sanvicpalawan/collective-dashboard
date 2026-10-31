from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


class LeadSearchRequest(BaseModel):
    """What the dashboard asks for: "find me {niche} in {location}"."""

    niche: str = Field(min_length=2, max_length=120)
    location: str = Field(min_length=2, max_length=120)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LeadRead(BaseModel):
    id: UUID
    business_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    status: str
    niche: Optional[str] = None
    location: Optional[str] = None
    source: Optional[str] = None
    job_id: Optional[UUID] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True
    )


class LeadJobRead(BaseModel):
    """A queued/running/finished lead-generation job, as the UI polls it."""

    id: UUID
    job_type: str
    status: str
    payload: Optional[dict] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True
    )
