"""Rule-based expansion of a periodized plan into daily planned workouts.

Pure core (no DB): given the plan's weeks + FTP, decide one structured workout
per training day. Reuses app.services.workout templates so each day is a real,
exportable structured workout. See the plan doc for the allocation rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.models.enums import BlockType, WorkoutType
from app.services.workout import analysis, templates
from app.services.workout.model import StructuredWorkout


@dataclass
class WeekSpec:
    week_start: date
    block_type: BlockType
    planned_tss: float
    is_recovery_week: bool


@dataclass
class DailyPlanned:
    planned_date: date
    workout_type: WorkoutType
    planned_duration_s: int
    planned_tss: float
    description: str
    structure: dict


# Role -> (template fn, WorkoutType)
_ROLE_ENDURANCE = (templates.endurance, WorkoutType.ENDURANCE)
_ROLE_SWEET = (templates.sweet_spot, WorkoutType.SWEET_SPOT)
_ROLE_VO2 = (templates.vo2max, WorkoutType.VO2MAX)
_ROLE_RECOVERY = (templates.recovery, WorkoutType.RECOVERY)
_ROLE_OPENERS = (templates.openers, WorkoutType.VO2MAX)

# Quality day positions (index among the week's training days) per block type.
_QUALITY_BY_BLOCK: dict[BlockType, list[tuple]] = {
    BlockType.BASE: [(1, _ROLE_SWEET)],
    BlockType.BUILD: [(0, _ROLE_VO2), (2, _ROLE_SWEET)],
    BlockType.PEAK: [(0, _ROLE_VO2), (2, _ROLE_VO2)],
    BlockType.TAPER: [(0, _ROLE_OPENERS)],
    BlockType.RECOVERY: [],
}


def _scaled_endurance(ftp: float, target_tss: float) -> StructuredWorkout:
    """Endurance workout whose duration is scaled to approximate target_tss."""
    w = templates.endurance(ftp)
    base_tss = analysis.estimated_tss(w)
    if base_tss <= 0 or target_tss <= 0:
        return w
    factor = max(0.5, min(2.5, target_tss / base_tss))
    # Scale the single long "active" step's duration (warmup/cooldown unchanged).
    # StructuredWorkout uses Pydantic BaseModel (no frozen=True), so direct
    # field assignment is permitted.
    for el in w.elements:
        if getattr(el, "intensity", None) == "active":
            el.duration_s = int(el.duration_s * factor)
    return w


def allocate_days(
    weeks: list[WeekSpec], ftp: float, race_date: date, rest_per_week: int, today: date
) -> list[DailyPlanned]:
    rest_per_week = max(0, min(3, rest_per_week))
    out: list[DailyPlanned] = []
    for wk in weeks:
        day_dates = [wk.week_start + timedelta(days=i) for i in range(7)]
        day_dates = [d for d in day_dates if today <= d <= race_date]
        if not day_dates:
            continue
        # First rest_per_week days of the (visible) week are rest.
        training = day_dates[rest_per_week:] if len(day_dates) > rest_per_week else []
        # Recovery week: all easy recovery.
        if wk.is_recovery_week:
            for d in training:
                out.append(_make(d, ftp, _ROLE_RECOVERY))
            continue
        quality_positions = dict(_QUALITY_BY_BLOCK.get(wk.block_type, []))
        quality_tss = 0.0
        endurance_idx: list[int] = []
        roles: dict[int, tuple] = {}
        for i in range(len(training)):
            if i in quality_positions:
                roles[i] = quality_positions[i]
            else:
                endurance_idx.append(i)
        # Estimate quality TSS to distribute the remainder to endurance days.
        for i, role in roles.items():
            quality_tss += analysis.estimated_tss(role[0](ftp))
        remaining = max(0.0, wk.planned_tss - quality_tss)
        per_endurance = remaining / len(endurance_idx) if endurance_idx else 0.0
        for i, d in enumerate(training):
            if i in roles:
                out.append(_make(d, ftp, roles[i]))
            else:
                w = _scaled_endurance(ftp, per_endurance)
                w.ftp_watts = ftp
                w.estimated_tss = analysis.estimated_tss(w)
                out.append(_daily_from(d, w, WorkoutType.ENDURANCE))
    return out


def _make(d: date, ftp: float, role: tuple) -> DailyPlanned:
    fn, wtype = role
    w = fn(ftp)
    w.ftp_watts = ftp
    w.estimated_tss = analysis.estimated_tss(w)
    return _daily_from(d, w, wtype)


def _daily_from(d: date, w: StructuredWorkout, wtype: WorkoutType) -> DailyPlanned:
    return DailyPlanned(
        planned_date=d,
        workout_type=wtype,
        planned_duration_s=analysis.total_duration_s(w),
        planned_tss=round(analysis.estimated_tss(w), 1),
        description=analysis.describe(w),
        structure=w.model_dump(),
    )


async def expand_plan_to_daily(session, ctx, athlete_id, plan_id) -> dict:
    """Persist one structured planned workout per training day for ``plan_id``.

    Idempotent: drops the rows previously generated from this plan
    (``source_plan_id == plan_id``) and recreates them; rows with a NULL
    ``source_plan_id`` (manual workouts / recommendations) are never touched.
    Tenant-scoped via ``athlete_id``. Returns a result dict, or ``{"error": ...}``
    so the caller can map it to an HTTP status.
    """
    from datetime import date as _date

    from sqlalchemy import delete, select

    from app.models.training_plan import TrainingPlan, TrainingWeek
    from app.models.workout import WorkoutPlanned
    from app.repositories.metrics_repo import FtpRepository
    from app.services.ai.profile_context import fetch_profile

    plan = (await session.execute(
        select(TrainingPlan).where(
            TrainingPlan.id == plan_id,
            TrainingPlan.athlete_id == athlete_id,
            TrainingPlan.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if plan is None:
        return {"error": "not_found"}
    today = _date.today()
    if plan.race_date is None or plan.race_date < today:
        return {"error": "race_past"}

    weeks_rows = (await session.execute(
        select(TrainingWeek)
        .where(TrainingWeek.plan_id == plan_id)
        .order_by(TrainingWeek.week_index)
    )).scalars().all()
    weeks = [
        WeekSpec(w.week_start, w.block_type, w.planned_tss or 0.0, bool(w.is_recovery_week))
        for w in weeks_rows
    ]

    ftp = await FtpRepository(session, ctx).value_on(today, athlete_id) or 200.0

    # Rest days/week derive from the athlete profile (7 - weekly_days), else 1.
    profile = await fetch_profile(session, athlete_id)
    rest = 1
    if profile is not None and profile.weekly_days:
        rest = max(0, min(3, 7 - int(profile.weekly_days)))

    days = allocate_days(
        weeks, ftp=ftp, race_date=plan.race_date, rest_per_week=rest, today=today
    )

    # Idempotent replace: drop this plan's existing daily rows, recreate.
    await session.execute(
        delete(WorkoutPlanned).where(
            WorkoutPlanned.athlete_id == athlete_id,
            WorkoutPlanned.source_plan_id == plan_id,
        )
    )
    for d in days:
        session.add(WorkoutPlanned(
            athlete_id=athlete_id, created_by=athlete_id,
            planned_date=d.planned_date, name=d.structure.get("name", "Treino"),
            workout_type=d.workout_type, planned_duration_s=d.planned_duration_s,
            planned_tss=d.planned_tss, structure=d.structure, description=d.description,
            source_plan_id=plan_id,
        ))
    await session.flush()
    return {
        "days": len(days),
        "tss_total": round(sum(d.planned_tss for d in days), 1),
        "start": str(min((d.planned_date for d in days), default=today)),
        "end": str(max((d.planned_date for d in days), default=today)),
    }
