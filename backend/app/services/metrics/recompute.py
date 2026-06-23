"""Recompute and persist the athlete's daily load series from their workouts."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.metrics import LoadMetric
from app.repositories.metrics_repo import LoadMetricRepository
from app.repositories.workout_repo import WorkoutRepository
from app.services.metrics.load_calculator import compute_load_series


async def recompute_load_metrics(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    lookback_days: int = 400,
) -> int:
    """Rebuild load_metrics for an athlete from completed workouts.

    Aggregates TSS per day, runs the PMC model and upserts one row per day.
    Returns the number of days written.
    """
    workout_repo = WorkoutRepository(session, ctx)
    load_repo = LoadMetricRepository(session, ctx)

    end = date.today()
    start = end - timedelta(days=lookback_days)
    workouts = await workout_repo.list_between(start, end, athlete_id)

    tss_by_date: dict[date, float] = {}
    for w in workouts:
        if w.tss:
            tss_by_date[w.workout_date] = tss_by_date.get(w.workout_date, 0.0) + w.tss

    if not tss_by_date:
        return 0

    series = compute_load_series(tss_by_date, start=min(tss_by_date), end=end)

    written = 0
    for day in series:
        existing = await load_repo.get_by_date(day.metric_date, athlete_id)
        if existing:
            existing.daily_tss = day.daily_tss
            existing.ctl = day.ctl
            existing.atl = day.atl
            existing.tsb = day.tsb
            existing.monotony = day.monotony
            existing.strain = day.strain
            session.add(existing)
        else:
            await load_repo.add(
                LoadMetric(
                    athlete_id=athlete_id,
                    metric_date=day.metric_date,
                    daily_tss=day.daily_tss,
                    ctl=day.ctl,
                    atl=day.atl,
                    tsb=day.tsb,
                    monotony=day.monotony,
                    strain=day.strain,
                )
            )
        written += 1
    await session.flush()
    return written
