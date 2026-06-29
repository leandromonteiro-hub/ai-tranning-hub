from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.models.metrics import LoadMetric
from app.models.race import Race
from app.repositories.plan_repo import PlannedWorkoutRepository
from app.repositories.workout_repo import WorkoutRepository
from app.schemas.calendar import (
    CalendarDay,
    CalendarResponse,
    RaceMarker,
    WeekSummary,
)
from app.schemas.planning import PlannedWorkoutRead
from app.schemas.workout import WorkoutCompletedRead

router = APIRouter(prefix="/calendar", tags=["calendar"])


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


@router.get("", response_model=CalendarResponse)
async def get_calendar(
    start: date = Query(...),
    end: date = Query(...),
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> CalendarResponse:
    completed = await WorkoutRepository(db, ctx).list_between(start, end)
    planned = await PlannedWorkoutRepository(db, ctx).list_between(start, end)

    # Fetch upcoming races starting from view start (not capped at end so races
    # just outside the view window still appear as markers on view days).
    races_stmt = (
        select(Race)
        .where(Race.deleted_at.is_(None), Race.athlete_id == ctx.athlete_id,
               Race.race_date >= start)
    )
    races = list((await db.execute(races_stmt)).scalars().all())

    load_stmt = (
        select(LoadMetric)
        .where(LoadMetric.deleted_at.is_(None), LoadMetric.athlete_id == ctx.athlete_id,
               LoadMetric.metric_date >= start, LoadMetric.metric_date <= end)
    )
    loads = {lm.metric_date: lm for lm in (await db.execute(load_stmt)).scalars().all()}

    by_day_planned: dict[date, list] = defaultdict(list)
    for p in planned:
        by_day_planned[p.planned_date].append(p)
    by_day_completed: dict[date, list] = defaultdict(list)
    for c in completed:
        by_day_completed[c.workout_date].append(c)

    days: list[CalendarDay] = []
    week_acc: dict[date, dict] = {}
    d = start
    while d <= end:
        day_completed = by_day_completed.get(d, [])
        # Each upcoming race appears as a marker on every view day before race day
        day_races = [rc for rc in races if d < rc.race_date]
        days.append(CalendarDay(
            date=d,
            planned=[PlannedWorkoutRead.model_validate(p) for p in by_day_planned.get(d, [])],
            completed=[WorkoutCompletedRead.model_validate(c) for c in day_completed],
            races=[RaceMarker(id=rc.id, name=rc.name, race_date=rc.race_date,
                              days_until=(rc.race_date - d).days) for rc in day_races],
        ))
        wk = week_acc.setdefault(_monday(d), {
            "total_duration_s": 0, "total_tss": 0.0, "total_distance_m": 0.0,
            "total_elevation_m": 0.0, "total_kj": 0.0, "ctl": None, "atl": None, "tsb": None,
        })
        for c in day_completed:
            wk["total_duration_s"] += c.duration_s or 0
            wk["total_tss"] += c.tss or 0.0
            wk["total_distance_m"] += c.distance_m or 0.0
            wk["total_elevation_m"] += c.elevation_gain_m or 0.0
            wk["total_kj"] += c.kj or 0.0
        lm = loads.get(d)
        if lm is not None:  # último valor PMC da semana representa Fitness/Fatigue/Form
            wk["ctl"], wk["atl"], wk["tsb"] = lm.ctl, lm.atl, lm.tsb
        d += timedelta(days=1)

    weeks = [WeekSummary(week_start=ws, **vals) for ws, vals in sorted(week_acc.items())]
    return CalendarResponse(days=days, weeks=weeks)
