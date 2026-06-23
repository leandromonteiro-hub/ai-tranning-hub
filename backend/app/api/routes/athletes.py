"""Athlete profile CRUD (self-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.models.athlete import AthleteProfile
from app.repositories.athlete_repo import AthleteRepository
from app.schemas.athlete import (
    AthleteProfileRead,
    AthleteProfileUpdate,
    AthleteRead,
)
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/athletes", tags=["athletes"])


@router.get("/me", response_model=AthleteRead)
async def get_me(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AthleteRead:
    athlete = await AthleteRepository(db).get(user.athlete_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    return AthleteRead.model_validate(athlete)


@router.get("/me/profile", response_model=AthleteProfileRead | None)
async def get_profile(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AthleteProfile).where(
        AthleteProfile.athlete_id == ctx.athlete_id,
        AthleteProfile.deleted_at.is_(None),
    )
    res = await db.execute(stmt)
    profile = res.scalar_one_or_none()
    return AthleteProfileRead.model_validate(profile) if profile else None


@router.put("/me/profile", response_model=AthleteProfileRead)
async def upsert_profile(
    body: AthleteProfileUpdate,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> AthleteProfileRead:
    stmt = select(AthleteProfile).where(
        AthleteProfile.athlete_id == ctx.athlete_id,
        AthleteProfile.deleted_at.is_(None),
    )
    res = await db.execute(stmt)
    profile = res.scalar_one_or_none()
    data = body.model_dump(exclude_unset=True)
    if profile:
        for k, v in data.items():
            setattr(profile, k, v)
    else:
        profile = AthleteProfile(
            athlete_id=ctx.athlete_id, created_by=ctx.athlete_id, **data
        )
        db.add(profile)
    await db.flush()
    return AthleteProfileRead.model_validate(profile)
