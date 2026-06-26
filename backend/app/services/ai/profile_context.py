"""Athlete profile (anamnese) helpers for the recommendation pipeline.

Fetches the athlete's profile, decides whether the anamnese is complete enough
to allow recommendations, and renders a one-line summary injected into the LLM
prompt so recommendations are personalised.
"""
from __future__ import annotations

import uuid
from collections import Counter
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


def twin_seed_summary(profile: AthleteProfile | None) -> str:
    """One-line summary of the reverse-engineered training profile (twin_seed)
    for the LLM prompt. Returns 'n/d' until the analysis has been run.

    Surfaces the athlete's real intensity distribution, power-curve bests,
    periodization pattern and data richness so recommendations match how this
    athlete actually trains — not a generic template.
    """
    seed = getattr(profile, "twin_seed", None) if profile is not None else None
    if not seed:
        return "n/d"
    parts: list[str] = []

    split = seed.get("intensity_split")
    if split:
        z1 = round((split.get("z1_pct") or 0) * 100)
        z2 = round((split.get("z2_pct") or 0) * 100)
        z3 = round((split.get("z3_pct") or 0) * 100)
        label = split.get("label") or ""
        parts.append(f"Distribuição de intensidade {label}: Z1 {z1}% / Z2 {z2}% / Z3 {z3}%")

    bests = seed.get("power_curve_bests") or seed.get("best_marks")
    if isinstance(bests, dict) and bests:
        marks = ", ".join(f"{k} {round(float(v))}W" for k, v in bests.items())
        parts.append(f"Melhores marcas de potência: {marks}")

    blocks = seed.get("block_summary") or []
    if blocks:
        types = Counter(
            (b.get("block_type") or "").lower() for b in blocks if b.get("block_type")
        )
        pattern = ", ".join(f"{n}× {t}" for t, n in types.most_common())
        parts.append(f"Periodização real ({len(blocks)} blocos): {pattern}")

    dr = seed.get("data_richness") or {}
    if dr.get("score") is not None:
        parts.append(f"Riqueza dos dados: {dr.get('label') or ''} ({float(dr['score']):.2f})")

    tapers = seed.get("tapers") or []
    if tapers:
        t0 = tapers[0]
        tsb = t0.get("tsb_race")
        trend = t0.get("weekly_tss_trend") or []
        drop = ""
        if len(trend) >= 2 and trend[0]:
            drop = f", volume ↓ ~{round((1 - trend[-1] / trend[0]) * 100)}%"
        parts.append(
            f"Taper típico (n={len(tapers)}): TSB ~{round(tsb) if tsb is not None else '—'} "
            f"no dia da prova{drop}"
        )

    terms = seed.get("coach_terms") or []
    if terms:
        names = ", ".join(t[0] for t in terms[:8])
        parts.append(f"Terminologia do treinador: {names}")

    per = seed.get("periodization_summary") or {}
    if per.get("n_blocks"):
        meso = per.get("meso_length_days_typical")
        rec = per.get("recovery_blocks")
        meso_txt = f", mesos ~{meso}d" if meso else ""
        rec_txt = f", {rec} blocos regen" if rec else ""
        parts.append(f"Padrão de periodização ({per['n_blocks']} blocos{meso_txt}{rec_txt})")

    return " · ".join(parts) if parts else "n/d"


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
