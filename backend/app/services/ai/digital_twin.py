"""Digital Twin Athlete: assembles the current state snapshot used by the AI.

It composes load metrics, recovery and subjective data into both a human-readable
summary (for the prompt) and the structured ``AthleteSafetySnapshot`` consumed by
the guardrails. Built from real data only — no inference here.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.repositories.metrics_repo import (
    LoadMetricRepository,
    RecoveryRepository,
    SubjectiveRepository,
)
from app.services.ai.safety_validator import AthleteSafetySnapshot
from app.services.metrics.load_calculator import ramp_rate


@dataclass
class DigitalTwin:
    snapshot: AthleteSafetySnapshot
    summary: str


async def build_twin(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    as_of: date | None = None,
) -> DigitalTwin:
    as_of = as_of or date.today()
    load_repo = LoadMetricRepository(session, ctx)
    recovery_repo = RecoveryRepository(session, ctx)
    subjective_repo = SubjectiveRepository(session, ctx)

    series = await load_repo.list_between(as_of - timedelta(days=42), as_of, athlete_id)
    latest = series[-1] if series else None

    # Weekly load (current vs previous 7d windows)
    week_current = sum(s.daily_tss for s in series if s.metric_date > as_of - timedelta(days=7))
    week_previous = sum(
        s.daily_tss for s in series
        if as_of - timedelta(days=14) < s.metric_date <= as_of - timedelta(days=7)
    )

    # Convert load series into the shape ramp_rate() expects.
    rr = ramp_rate(series) if len(series) > 7 else None

    recovery = await recovery_repo.list_recent(as_of - timedelta(days=14), athlete_id)
    recent_sleep = None
    hrv_recent = None
    hrv_baseline = None
    if recovery:
        last2 = [r for r in recovery if r.metric_date >= as_of - timedelta(days=2)]
        sleeps = [r.sleep_hours for r in last2 if r.sleep_hours is not None]
        recent_sleep = min(sleeps) if sleeps else None
        hrvs = [r.hrv_ms for r in recovery if r.hrv_ms is not None]
        if hrvs:
            hrv_recent = hrvs[-1]
            hrv_baseline = sum(hrvs) / len(hrvs)

    subjective = await subjective_repo.list_recent(as_of - timedelta(days=3), athlete_id)
    fatigue = None
    recent_injury = False
    if subjective:
        fatigues = [s.fatigue for s in subjective if s.fatigue is not None]
        fatigue = max(fatigues) if fatigues else None
        recent_injury = any(s.injury_flag for s in subjective)

    # Consecutive high-load days
    consec = 0
    for s in reversed(series):
        if s.daily_tss >= 120:
            consec += 1
        else:
            break

    snapshot = AthleteSafetySnapshot(
        ctl=latest.ctl if latest else None,
        atl=latest.atl if latest else None,
        tsb=latest.tsb if latest else None,
        ramp_rate_7d=rr,
        monotony=latest.monotony if latest else None,
        weekly_tss_current=week_current or None,
        weekly_tss_previous=week_previous or None,
        last_48h_sleep_h=recent_sleep,
        hrv_recent=hrv_recent,
        hrv_baseline=hrv_baseline,
        subjective_fatigue=fatigue,
        recent_injury=recent_injury,
        consecutive_high_load_days=consec,
    )

    summary = _render_summary(snapshot)
    return DigitalTwin(snapshot=snapshot, summary=summary)


def _fmt(v, suffix: str = "") -> str:
    return f"{v:.1f}{suffix}" if isinstance(v, (int, float)) else "n/d"


def _render_summary(s: AthleteSafetySnapshot) -> str:
    return (
        f"CTL (fitness): {_fmt(s.ctl)} | ATL (fatigue): {_fmt(s.atl)} | "
        f"TSB (form): {_fmt(s.tsb)}\n"
        f"7d CTL ramp: {_fmt(s.ramp_rate_7d)} | monotony: {_fmt(s.monotony)}\n"
        f"Weekly TSS now/prev: {_fmt(s.weekly_tss_current)}/{_fmt(s.weekly_tss_previous)}\n"
        f"Sleep last 48h: {_fmt(s.last_48h_sleep_h, 'h')} | "
        f"HRV recent/baseline: {_fmt(s.hrv_recent)}/{_fmt(s.hrv_baseline)}\n"
        f"Subjective fatigue: {s.subjective_fatigue or 'n/d'}/5 | "
        f"recent injury: {s.recent_injury} | "
        f"consecutive high-load days: {s.consecutive_high_load_days}"
    )
