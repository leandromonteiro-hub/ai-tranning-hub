"""Race calendar, results and pre/post-race analyses (tenant-scoped)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.models.race import Race, RaceAnalysis, RaceResult
from app.repositories.base import TenantRepository
from app.schemas.race import (
    RaceAnalysisCreate,
    RaceAnalysisRead,
    RaceCreate,
    RaceRead,
    RaceResultCreate,
    RaceResultRead,
)

router = APIRouter(prefix="/races", tags=["races"])


class _RaceRepo(TenantRepository[Race]):
    model = Race


class _ResultRepo(TenantRepository[RaceResult]):
    model = RaceResult


class _AnalysisRepo(TenantRepository[RaceAnalysis]):
    model = RaceAnalysis


@router.post("", response_model=RaceRead, status_code=201)
async def create_race(
    body: RaceCreate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    race = await _RaceRepo(db, ctx).add(Race(athlete_id=ctx.athlete_id, **body.model_dump()))
    return RaceRead.model_validate(race)


@router.get("", response_model=list[RaceRead])
async def list_races(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    races = await _RaceRepo(db, ctx).list()
    return [RaceRead.model_validate(r) for r in sorted(races, key=lambda r: r.race_date)]


@router.post("/results", response_model=RaceResultRead, status_code=201)
async def add_result(
    body: RaceResultCreate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    # Ensure the race belongs to this tenant before attaching a result.
    if not await _RaceRepo(db, ctx).get(body.race_id):
        raise HTTPException(status_code=404, detail="Race not found")
    result = await _ResultRepo(db, ctx).add(
        RaceResult(athlete_id=ctx.athlete_id, **body.model_dump())
    )
    return RaceResultRead.model_validate(result)


@router.post("/analyses", response_model=RaceAnalysisRead, status_code=201)
async def add_analysis(
    body: RaceAnalysisCreate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    if not await _RaceRepo(db, ctx).get(body.race_id):
        raise HTTPException(status_code=404, detail="Race not found")
    analysis = await _AnalysisRepo(db, ctx).add(
        RaceAnalysis(athlete_id=ctx.athlete_id, author="athlete", **body.model_dump())
    )
    return RaceAnalysisRead.model_validate(analysis)


@router.get("/{race_id}/analyses", response_model=list[RaceAnalysisRead])
async def list_analyses(
    race_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(RaceAnalysis)
        .where(RaceAnalysis.athlete_id == ctx.athlete_id)
        .where(RaceAnalysis.race_id == race_id)
        .where(RaceAnalysis.deleted_at.is_(None))
    )
    res = await db.execute(stmt)
    return [RaceAnalysisRead.model_validate(a) for a in res.scalars().all()]
