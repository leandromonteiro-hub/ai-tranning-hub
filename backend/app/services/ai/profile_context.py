"""Athlete profile (anamnese) helpers for the recommendation pipeline.

Fetches the athlete's profile, decides whether the anamnese is complete enough
to allow recommendations, and renders a one-line summary injected into the LLM
prompt so recommendations are personalised.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import AthleteProfile

# Single source of truth for "anamnese complete" (mirrored in the frontend).
REQUIRED_FIELDS = (
    "birth_date", "sex", "weight_kg", "height_cm", "max_hr",
    "primary_discipline", "years_training", "goals", "weekly_hours",
)


async def fetch_profile(session: AsyncSession, athlete_id: uuid.UUID) -> AthleteProfile | None:
    res = await session.execute(
        select(AthleteProfile).where(
            AthleteProfile.athlete_id == athlete_id,
            AthleteProfile.deleted_at.is_(None),
        )
    )
    return res.scalar_one_or_none()


def anamnese_complete(profile: AthleteProfile | None) -> bool:
    if profile is None:
        return False
    return all(getattr(profile, f) not in (None, "") for f in REQUIRED_FIELDS)


def profile_summary(profile: AthleteProfile | None) -> str:
    if profile is None:
        return "n/d"
    parts: list[str] = []
    if profile.birth_date:
        parts.append(f"{(date.today() - profile.birth_date).days // 365} anos")
    if profile.sex:
        parts.append(profile.sex)
    if profile.weight_kg:
        parts.append(f"{profile.weight_kg:.0f}kg")
    if profile.height_cm:
        parts.append(f"{profile.height_cm:.0f}cm")
    if profile.max_hr:
        parts.append(f"FCmax {profile.max_hr}")
    if profile.resting_hr:
        parts.append(f"FCrep {profile.resting_hr}")
    if profile.years_training is not None:
        parts.append(f"{profile.years_training} anos de treino")
    if profile.primary_discipline:
        parts.append(profile.primary_discipline)
    line = ", ".join(parts) if parts else "n/d"

    extra: list[str] = []
    if profile.goals:
        extra.append(f"Objetivos: {profile.goals}")
    if profile.weekly_hours is not None:
        days = f", {profile.weekly_days}d" if profile.weekly_days else ""
        extra.append(f"Disponibilidade: {profile.weekly_hours:.0f}h/sem{days}")
    if profile.injury_history:
        extra.append(f"Lesões/limitações: {profile.injury_history}")
    if profile.medical_conditions:
        extra.append(f"Condições médicas: {profile.medical_conditions}")
    equip = [n for n, v in (("potência", profile.has_power_meter), ("FC", profile.has_hr_monitor)) if v]
    if equip:
        extra.append("Equipamento: " + "+".join(equip))
    return line + ((" · " + " · ".join(extra)) if extra else "")
