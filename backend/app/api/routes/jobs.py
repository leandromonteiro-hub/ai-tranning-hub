"""Async job-status endpoint (Celery AsyncResult — state only)."""
from __future__ import annotations

from celery.result import AsyncResult
from fastapi import APIRouter, Depends

from app.api.deps import get_tenant
from app.core.tenant import TenantContext
from app.jobs.celery_app import celery
from app.schemas.jobs import JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{task_id}", response_model=JobStatus)
async def job_status(
    task_id: str,
    ctx: TenantContext = Depends(get_tenant),
) -> JobStatus:
    """Return only the Celery task state. Never the result payload — the task_id
    is an opaque UUID and the state leaks nothing cross-tenant; the client
    re-fetches its own tenant-scoped profile (via /athletes/me/intelligence)
    on SUCCESS."""
    res = AsyncResult(task_id, app=celery)
    return JobStatus(task_id=task_id, state=res.state)
