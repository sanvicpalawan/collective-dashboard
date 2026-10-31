
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.dependencies import DBSession, get_current_user, CurrentUser
from app.core.exceptions import NotFoundException
from app.schemas.leads_schemas import LeadJobRead, LeadRead, LeadSearchRequest
from app.services.leads_service import LeadsService

router = APIRouter(prefix="/api/leads", tags=["Leads"])


@router.get("", response_model=List[LeadRead])
async def list_leads(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: DBSession,
    limit: int = 200,
    offset: int = 0,
):
    """Leads for the caller's tenant, newest first."""
    limit = max(1, min(limit, 500))
    return await LeadsService(db).list_leads(current_user.tenant_id, limit, offset)


@router.post("/find", response_model=LeadJobRead, status_code=202)
async def find_leads(
    payload: LeadSearchRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: DBSession,
):
    """Queue a lead-generation search. Poll `/api/leads/jobs/{id}` for progress."""
    return await LeadsService(db).enqueue_search(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        niche=payload.niche.strip(),
        location=payload.location.strip(),
    )


@router.get("/jobs/{job_id}", response_model=LeadJobRead)
async def get_lead_job(
    job_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: DBSession,
):
    job = await LeadsService(db).get_job(current_user.tenant_id, job_id)
    if not job:
        raise NotFoundException("Lead search not found")
    return job
