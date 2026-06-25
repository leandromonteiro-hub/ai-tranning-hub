"""Athlete profile CRUD (self-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.models.athlete import AthleteProfile
from app.models.metrics import FtpHistory, LoadMetric
from app.repositories.athlete_repo import AthleteRepository
from app.schemas.athlete import (
    AthleteIntelligenceRead,
    AthleteProfileRead,
    AthleteProfileUpdate,
    AthleteRead,
    FormState,
    FtpPoint,
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


@router.get("/me/intelligence", response_model=AthleteIntelligenceRead)
async def get_intelligence(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> AthleteIntelligenceRead:
    """The athlete's computed training intelligence: reverse-engineered profile
    (twin_seed), FTP timeline, and current form (CTL/ATL/TSB)."""
    prof = (await db.execute(
        select(AthleteProfile).where(
            AthleteProfile.athlete_id == ctx.athlete_id,
            AthleteProfile.deleted_at.is_(None),
        )
    )).scalar_one_or_none()

    ftps = (await db.execute(
        select(FtpHistory).where(
            FtpHistory.athlete_id == ctx.athlete_id,
            FtpHistory.deleted_at.is_(None),
        ).order_by(FtpHistory.valid_from)
    )).scalars().all()

    latest = (await db.execute(
        select(LoadMetric).where(
            LoadMetric.athlete_id == ctx.athlete_id,
            LoadMetric.deleted_at.is_(None),
        ).order_by(LoadMetric.metric_date.desc()).limit(1)
    )).scalar_one_or_none()

    return AthleteIntelligenceRead(
        twin_seed=prof.twin_seed if prof else None,
        ftp_history=[FtpPoint.model_validate(f) for f in ftps],
        form=FormState.model_validate(latest) if latest else None,
    )


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
