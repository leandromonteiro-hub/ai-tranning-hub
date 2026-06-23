"""Load series, FTP history and recovery/subjective metric endpoints."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.models.metrics import FtpHistory, RecoveryMetric, SubjectiveMetric
from app.repositories.metrics_repo import (
    FtpRepository,
    LoadMetricRepository,
)
from app.schemas.metrics import (
    FtpCreate,
    FtpRead,
    LoadMetricRead,
    RecoveryCreate,
    SubjectiveCreate,
)
from app.services.metrics.recompute import recompute_load_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/load", response_model=list[LoadMetricRead])
async def get_load(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    repo = LoadMetricRepository(db, ctx)
    end = end or date.today()
    start = start or (end - timedelta(days=90))
    return [LoadMetricRead.model_validate(m) for m in await repo.list_between(start, end)]


@router.post("/load/recompute")
async def recompute(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    days = await recompute_load_metrics(db, ctx, ctx.athlete_id)
    return {"days_written": days}


@router.post("/ftp", response_model=FtpRead, status_code=201)
async def add_ftp(
    body: FtpCreate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    repo = FtpRepository(db, ctx)
    # Close the previous open-ended FTP range the day before the new one starts.
    current = await repo.list()
    for row in current:
        if row.valid_to is None and row.valid_from < body.valid_from:
            row.valid_to = body.valid_from - timedelta(days=1)
            db.add(row)
    ftp = FtpHistory(
        athlete_id=ctx.athlete_id,
        ftp_watts=body.ftp_watts,
        valid_from=body.valid_from,
        method=body.method,
    )
    await repo.add(ftp)
    return FtpRead.model_validate(ftp)


@router.post("/recovery", status_code=201)
async def add_recovery(
    body: RecoveryCreate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    metric = RecoveryMetric(athlete_id=ctx.athlete_id, **body.model_dump())
    db.add(metric)
    await db.flush()
    return {"id": str(metric.id)}


@router.post("/subjective", status_code=201)
async def add_subjective(
    body: SubjectiveCreate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    metric = SubjectiveMetric(athlete_id=ctx.athlete_id, **body.model_dump())
    db.add(metric)
    await db.flush()
    return {"id": str(metric.id)}
