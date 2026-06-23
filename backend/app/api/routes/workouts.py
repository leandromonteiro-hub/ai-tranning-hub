"""Completed-workout CRUD (tenant-scoped)."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.models.workout import WorkoutCompleted
from app.repositories.metrics_repo import FtpRepository
from app.repositories.workout_repo import WorkoutRepository
from app.schemas.workout import WorkoutCompletedCreate, WorkoutCompletedRead
from app.services.metrics import tss_calculator

router = APIRouter(prefix="/workouts", tags=["workouts"])


@router.get("", response_model=list[WorkoutCompletedRead])
async def list_workouts(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    repo = WorkoutRepository(db, ctx)
    end = end or date.today()
    start = start or (end - timedelta(days=90))
    workouts = await repo.list_between(start, end)
    return [WorkoutCompletedRead.model_validate(w) for w in workouts]


@router.post("", response_model=WorkoutCompletedRead, status_code=201)
async def create_workout(
    body: WorkoutCompletedCreate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    repo = WorkoutRepository(db, ctx)
    ftp_repo = FtpRepository(db, ctx)
    wdate = body.started_at.date()
    ftp = await ftp_repo.value_on(wdate)

    intf = tss_calculator.intensity_factor(body.normalized_power, ftp)
    tss = tss_calculator.tss_from_np(body.duration_s, body.normalized_power, ftp)

    workout = WorkoutCompleted(
        athlete_id=ctx.athlete_id,
        started_at=body.started_at,
        workout_date=wdate,
        name=body.name,
        workout_type=body.workout_type,
        sport=body.sport,
        duration_s=body.duration_s,
        distance_m=body.distance_m,
        elevation_gain_m=body.elevation_gain_m,
        avg_power=body.avg_power,
        normalized_power=body.normalized_power,
        avg_hr=body.avg_hr,
        max_hr=body.max_hr,
        avg_cadence=body.avg_cadence,
        intensity_factor=intf,
        tss=tss,
        ftp_used=ftp,
        external_id=body.external_id,
        notes=body.notes,
    )
    await repo.add(workout)
    return WorkoutCompletedRead.model_validate(workout)


@router.get("/{workout_id}", response_model=WorkoutCompletedRead)
async def get_workout(
    workout_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    repo = WorkoutRepository(db, ctx)
    workout = await repo.get(workout_id)
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    return WorkoutCompletedRead.model_validate(workout)


@router.delete("/{workout_id}", status_code=204)
async def delete_workout(
    workout_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    repo = WorkoutRepository(db, ctx)
    workout = await repo.get(workout_id)
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    await repo.soft_delete(workout)  # soft delete only — never physical
