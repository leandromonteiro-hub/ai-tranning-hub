"""Training plan generation and retrieval."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.models.training_plan import TrainingPlan
from app.repositories.base import TenantRepository
from app.schemas.planning import (
    PlanExpandResult,
    PlanGenerateRequest,
    TrainingPlanRead,
)
from app.services.planning.plan_expander import expand_plan_to_daily
from app.services.planning.plan_service import generate_plan

router = APIRouter(prefix="/plans", tags=["plans"])


class _PlanRepo(TenantRepository[TrainingPlan]):
    model = TrainingPlan


@router.post("/generate", response_model=TrainingPlanRead, status_code=201)
async def generate(
    body: PlanGenerateRequest,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    plan = await generate_plan(
        db, ctx, ctx.athlete_id,
        race_date=body.race_date, name=body.name,
        target_race_id=body.target_race_id, priority=body.priority,
        start_date=body.start_date,
    )
    await db.refresh(plan, attribute_names=["blocks", "weeks"])
    return TrainingPlanRead.model_validate(plan)


@router.get("", response_model=list[TrainingPlanRead])
async def list_plans(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    plans = await _PlanRepo(db, ctx).list()
    out = []
    for p in plans:
        await db.refresh(p, attribute_names=["blocks", "weeks"])
        out.append(TrainingPlanRead.model_validate(p))
    return out


@router.post("/{plan_id}/expand", response_model=PlanExpandResult, status_code=201)
async def expand_plan(
    plan_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate one structured planned workout per day from the periodized plan
    until the race (rule-based, idempotent)."""
    result = await expand_plan_to_daily(db, ctx, ctx.athlete_id, plan_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    if result.get("error") == "race_past":
        raise HTTPException(status_code=400, detail="A prova já ocorreu ou não tem data")
    return PlanExpandResult(**result)


@router.get("/{plan_id}", response_model=TrainingPlanRead)
async def get_plan(
    plan_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    plan = await _PlanRepo(db, ctx).get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    await db.refresh(plan, attribute_names=["blocks", "weeks"])
    return TrainingPlanRead.model_validate(plan)
