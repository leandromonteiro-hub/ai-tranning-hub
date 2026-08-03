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


# ---- Esqueleto semanal (spec 2026-08-03) ------------------------------------
# Papéis por dia da semana (0=seg .. 6=dom). Descansos na ordem seg, sex, sáb.
_REST_ORDER = (0, 4, 5)

_SKELETON: dict[BlockType, dict[int, str]] = {
    BlockType.BASE:     {1: "q1", 2: "z2var", 3: "q2", 4: "easy", 5: "short_z2", 6: "long"},
    BlockType.BUILD:    {1: "q1", 2: "z2var", 3: "q2", 4: "easy", 5: "short_z2", 6: "long"},
    BlockType.PEAK:     {1: "q1", 2: "z2var", 3: "q2", 4: "easy", 5: "easy", 6: "long"},
    BlockType.TAPER:    {2: "openers", 3: "short_z2", 4: "easy", 6: "short_z2"},
    BlockType.RECOVERY: {1: "easy", 2: "easy_z2", 3: "easy", 5: "easy_z2", 6: "short_z2"},
}

_QUALITY: dict[BlockType, dict[str, tuple]] = {
    BlockType.BASE:  {"q1": (templates.sweet_spot, WorkoutType.SWEET_SPOT),
                      "q2": (templates.forca_cadencia, WorkoutType.TEMPO)},
    BlockType.BUILD: {"q1": (templates.vo2max, WorkoutType.VO2MAX),
                      "q2": (templates.tempo, WorkoutType.TEMPO)},
    BlockType.PEAK:  {"q1": (templates.vo2max, WorkoutType.VO2MAX),
                      "q2": (templates.vo2max, WorkoutType.VO2MAX)},
}

_Z2_ROTATION = (templates.z2_sprints, templates.z2_progressivo, templates.endurance)

_LONG_SHARE = {BlockType.BASE: 0.40, BlockType.BUILD: 0.40, BlockType.PEAK: 0.30}
_LONG_MIN_S = 2 * 3600
_LONG_MAX_S = 5 * 3600
_SHORT_Z2_CAP_S = 75 * 60


def _long_for_tss(block: BlockType, ftp: float, target_tss: float) -> StructuredWorkout:
    """Longão (Z2 puro; com tempo no BUILD) com duração dimensionada pelo TSS alvo."""
    fn = templates.long_ride_tempo if block == BlockType.BUILD else templates.long_ride
    probe = fn(ftp, _LONG_MIN_S)
    if_ = analysis.intensity_factor(probe)
    dur = _LONG_MIN_S if if_ <= 0 else int(target_tss / ((if_ ** 2) * 100) * 3600)
    dur = max(_LONG_MIN_S, min(_LONG_MAX_S, dur))
    return fn(ftp, dur)


def _scaled_endurance_capped(ftp: float, target_tss: float, cap_s: int) -> StructuredWorkout:
    """Endurance Z2 escalado ao TSS alvo, nunca passando de ``cap_s`` no total."""
    w = templates.endurance(ftp)
    base = analysis.estimated_tss(w)
    factor = 1.0 if base <= 0 or target_tss <= 0 else max(0.5, target_tss / base)
    for el in w.elements:
        if getattr(el, "intensity", None) == "active":
            el.duration_s = int(el.duration_s * factor)
    excess = analysis.total_duration_s(w) - cap_s
    if excess > 0:
        for el in w.elements:
            if getattr(el, "intensity", None) == "active":
                el.duration_s = max(600, el.duration_s - excess)
    return w


def _with_meta(w: StructuredWorkout, ftp: float) -> StructuredWorkout:
    w.ftp_watts = ftp
    w.estimated_tss = analysis.estimated_tss(w)
    return w


def allocate_days(
    weeks: list[WeekSpec], ftp: float, race_date: date, rest_per_week: int, today: date,
    blocked_days: frozenset[date] = frozenset(),
) -> tuple[list[DailyPlanned], float]:
    rest = max(1, min(3, rest_per_week))
    rest_days = set(_REST_ORDER[:rest])
    out: list[DailyPlanned] = []
    dropped_total = 0.0

    for i, wk in enumerate(weeks):
        visible = [wk.week_start + timedelta(days=j) for j in range(7)]
        # Dia de prova nunca recebe treino prescrito (spec 2026-08-02).
        visible = [d for d in visible if today <= d <= race_date and d not in blocked_days]
        if not visible:
            continue

        skel = _SKELETON.get(wk.block_type, _SKELETON[BlockType.BASE])
        roles: dict[date, str] = {}
        for d in visible:
            wd = d.weekday()
            if wd in rest_days:
                continue
            role = skel.get(wd)
            if role:
                roles[d] = role

        # Semana da prova: openers em prova-2; entre openers e prova, regenerativo.
        # O openers fixo do esqueleto TAPER (qua) vira Z2 curto para não duplicar.
        if wk.week_start <= race_date <= wk.week_start + timedelta(days=6):
            op = race_date - timedelta(days=2)
            for d in list(roles):
                if d >= op:
                    del roles[d]
                elif roles[d] == "openers":
                    roles[d] = "short_z2"
            if today <= op <= race_date and op not in blocked_days:
                roles[op] = "openers"
                mid = op + timedelta(days=1)
                if today <= mid < race_date and mid not in blocked_days:
                    roles[mid] = "easy"

        # 1) Dias de papel fixo.
        fixed: dict[date, tuple[StructuredWorkout, WorkoutType]] = {}
        long_day = next((d for d, r in roles.items() if r == "long"), None)
        short_days = [d for d, r in roles.items() if r == "short_z2"]
        for d, r in roles.items():
            if r in ("long", "short_z2"):
                continue
            if r in ("q1", "q2"):
                fn, wtype = _QUALITY[wk.block_type][r]
                fixed[d] = (fn(ftp), wtype)
            elif r == "openers":
                fixed[d] = (templates.openers(ftp), WorkoutType.VO2MAX)
            elif r == "easy":
                fixed[d] = (templates.recovery(ftp), WorkoutType.RECOVERY)
            elif r == "easy_z2":
                fixed[d] = (templates.endurance(ftp), WorkoutType.ENDURANCE)
            elif r == "z2var":
                fixed[d] = (_Z2_ROTATION[i % len(_Z2_ROTATION)](ftp), WorkoutType.ENDURANCE)
        fixed_tss = sum(analysis.estimated_tss(w) for w, _ in fixed.values())

        # 2) Longão (40% / 30% do TSS semanal) e Z2 curto absorvem o restante.
        loading = wk.block_type in _LONG_SHARE and not wk.is_recovery_week
        long_w: StructuredWorkout | None = None
        long_tss = 0.0
        if long_day is not None and loading:
            long_w = _long_for_tss(wk.block_type, ftp, wk.planned_tss * _LONG_SHARE[wk.block_type])
            long_tss = analysis.estimated_tss(long_w)
        short_w: StructuredWorkout | None = None
        if short_days:
            # O restante divide igual entre os dias de Z2 curto.
            target = 0.0
            if loading:
                target = max(0.0, wk.planned_tss - fixed_tss - long_tss) / len(short_days)
            short_w = _scaled_endurance_capped(ftp, target, _SHORT_Z2_CAP_S)

        # 3) Excedente volta ao longão (até 5h); o resto é descartado e reportado.
        if loading:
            short_tss = (analysis.estimated_tss(short_w) if short_w else 0.0) * len(short_days)
            leftover = wk.planned_tss - fixed_tss - long_tss - short_tss
            if leftover > 0 and long_w is not None:
                long_w = _long_for_tss(wk.block_type, ftp, long_tss + leftover)
                long_tss = analysis.estimated_tss(long_w)
                leftover = wk.planned_tss - fixed_tss - long_tss - short_tss
            dropped_total += max(0.0, leftover)

        for d in sorted(roles):
            if d == long_day and long_w is not None:
                out.append(_daily_from(d, _with_meta(long_w, ftp), WorkoutType.ENDURANCE))
            elif d in short_days and short_w is not None:
                out.append(_daily_from(d, _with_meta(short_w, ftp), WorkoutType.ENDURANCE))
            elif d in fixed:
                w, wtype = fixed[d]
                out.append(_daily_from(d, _with_meta(w, ftp), wtype))
    return out, round(dropped_total, 1)


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

    from app.models.race import Race
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

    # Dias de prova cadastrada (qualquer prioridade) não recebem treino.
    races = (await session.execute(
        select(Race).where(Race.athlete_id == athlete_id, Race.deleted_at.is_(None))
    )).scalars().all()
    blocked: set[date] = set()
    for rc in races:
        last = rc.end_date or rc.race_date
        dd = rc.race_date
        while dd <= last:
            blocked.add(dd)
            dd += timedelta(days=1)

    days = allocate_days(
        weeks, ftp=ftp, race_date=plan.race_date, rest_per_week=rest, today=today,
        blocked_days=frozenset(blocked),
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
