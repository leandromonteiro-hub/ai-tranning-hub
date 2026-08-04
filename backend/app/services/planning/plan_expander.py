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
from app.services.workout.model import Step, StructuredWorkout, Target


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


# ---- Esqueleto semanal (spec 2026-08-03, rev. 2026-08-04) -------------------
# Papéis por dia da semana (0=seg .. 6=dom). DOMINGO é sempre off (nenhum
# esqueleto prescreve o dia 6); dias de prova seguem bloqueados à parte.
# Descansos na ordem seg, sex, qua.
_REST_ORDER = (0, 4, 2)

_SKELETON: dict[BlockType, dict[int, str]] = {
    BlockType.BASE:     {1: "q1", 2: "z2var", 3: "q2", 4: "easy", 5: "long"},
    BlockType.BUILD:    {1: "q1", 2: "z2var", 3: "q2", 4: "easy", 5: "long"},
    BlockType.PEAK:     {1: "q1", 2: "z2var", 3: "q2", 4: "easy", 5: "long"},
    BlockType.TAPER:    {2: "openers", 3: "short_z2", 4: "easy", 5: "short_z2"},
    BlockType.RECOVERY: {1: "easy", 2: "easy_z2", 3: "easy", 5: "short_z2"},
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
_MIDWEEK_CAP_S = 210 * 60  # dia flex de quarta: até 3h30 (rev. 2026-08-04)
_FRIDAY_CAP_S = 120 * 60   # sexta Z2 leve em semana de carga: até 2h (rev. 2)
_DELOAD_DAY_CAP_S = 180 * 60  # dias de Z2 do deload: até 3h (rev. 2)
_ABSORB_MIN_TSS = 10.0     # sobra menor que isso não muda o desenho do dia
_Z2_TSS_PER_H = 42.25      # TSS/h a IF 0.65 (Z2 0,62-0,68)


def _pad_with_z2(w: StructuredWorkout, extra_tss: float, cap_s: int) -> StructuredWorkout:
    """Extensão Z2 após o trabalho principal (rev. 2 2026-08-04).

    Insere um bloco Z2 antes da volta à calma, dimensionado por ``extra_tss``,
    sem passar de ``cap_s`` no total. Sobras <10 min são ignoradas.
    """
    if extra_tss <= 0:
        return w
    add_s = int(extra_tss / _Z2_TSS_PER_H * 3600)
    add_s = min(add_s, cap_s - analysis.total_duration_s(w))
    if add_s < 600:
        return w
    step = Step(intensity="active", duration_s=add_s,
                target=Target(type="power_pct_ftp", low=0.62, high=0.68),
                note="Extensão Z2 após o trabalho principal")
    idx = next((k for k in range(len(w.elements) - 1, -1, -1)
                if getattr(w.elements[k], "intensity", None) == "cooldown"), None)
    if idx is None:
        w.elements.append(step)
    else:
        w.elements.insert(idx, step)
    return w


def _scaled_variant(fn, ftp: float, target_tss: float, cap_s: int) -> StructuredWorkout:
    """Variante de Z2 escalada ao TSS alvo, teto ``cap_s``.

    Alonga apenas blocos "active" de ≥10 min no nível raiz — sprints de 10s
    (dentro de Repeat) e aquecimento/volta à calma ficam intactos.
    """
    w = fn(ftp)
    scalable = [el for el in w.elements
                if getattr(el, "intensity", None) == "active" and el.duration_s >= 600]
    if not scalable:
        return w
    base = analysis.estimated_tss(w)
    factor = 1.0 if base <= 0 or target_tss <= 0 else max(0.5, target_tss / base)
    for el in scalable:
        el.duration_s = int(el.duration_s * factor)
    excess = analysis.total_duration_s(w) - cap_s
    if excess > 0:
        total = sum(el.duration_s for el in scalable)
        for el in scalable:
            el.duration_s = max(600, el.duration_s - int(excess * el.duration_s / total))
    return w


def _long_for_tss(block: BlockType, ftp: float, target_tss: float,
                  week_i: int = 0) -> StructuredWorkout:
    """Longão com duração dimensionada pelo TSS alvo.

    BUILD usa a variante com blocos de tempo; na BASE o Z2 puro alterna com o
    "com giros" semana a semana (rev. 3 2026-08-04); PEAK fica no Z2 puro.
    """
    if block == BlockType.BUILD:
        fn = templates.long_ride_tempo
    elif block == BlockType.BASE and week_i % 2 == 1:
        fn = templates.long_ride_giros
    else:
        fn = templates.long_ride
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
    # Degrau de progressão dos intervalados: avança a cada semana de carga do
    # mesmo bloco; reseta no deload ou na troca de bloco (rev. 3 2026-08-04).
    step = 0
    prev_block: BlockType | None = None

    for i, wk in enumerate(weeks):
        recovery_week = wk.is_recovery_week or wk.block_type == BlockType.RECOVERY
        if recovery_week or wk.block_type != prev_block:
            step = 0
        prev_block = wk.block_type

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

        # 1) Dias de papel fixo (qualidade, regenerativo, openers).
        assigned: dict[date, tuple[StructuredWorkout, WorkoutType]] = {}
        long_day = next((d for d, r in roles.items() if r == "long"), None)
        flex_day = next((d for d, r in roles.items() if r == "z2var"), None)
        short_days = [d for d, r in roles.items() if r == "short_z2"]
        easy_z2_days = [d for d, r in roles.items() if r == "easy_z2"]
        easy_days = [d for d, r in roles.items() if r == "easy"]
        quality_days = [d for d, r in roles.items() if r in ("q1", "q2")]
        for d, r in roles.items():
            if r in ("q1", "q2"):
                fn, wtype = _QUALITY[wk.block_type][r]
                assigned[d] = (fn(ftp, step), wtype)
            elif r == "openers":
                assigned[d] = (templates.openers(ftp), WorkoutType.VO2MAX)
            elif r == "easy":
                assigned[d] = (templates.recovery(ftp), WorkoutType.RECOVERY)

        def _delivered() -> float:
            return sum(analysis.estimated_tss(w) for w, _ in assigned.values())

        loading = wk.block_type in _LONG_SHARE and not wk.is_recovery_week

        if loading:
            # Ordem de absorção (rev. 2): longão 40% → quarta flex → sexta Z2
            # leve → extensões Z2 de ter/qui → longão de novo → descarte.
            if long_day is not None:
                assigned[long_day] = (
                    _long_for_tss(wk.block_type, ftp,
                                  wk.planned_tss * _LONG_SHARE[wk.block_type], week_i=i),
                    WorkoutType.ENDURANCE,
                )
            if flex_day is not None:
                variant = _Z2_ROTATION[i % len(_Z2_ROTATION)]
                target = max(0.0, wk.planned_tss - _delivered())
                assigned[flex_day] = (
                    _scaled_variant(variant, ftp, target, _MIDWEEK_CAP_S),
                    WorkoutType.ENDURANCE,
                )
            for d in short_days:  # só existe aqui via conversão da semana de prova
                target = max(0.0, wk.planned_tss - _delivered()) / len(short_days)
                assigned[d] = (_scaled_endurance_capped(ftp, target, _SHORT_Z2_CAP_S),
                               WorkoutType.ENDURANCE)
            leftover = wk.planned_tss - _delivered()
            if leftover > _ABSORB_MIN_TSS and easy_days:
                for d in easy_days:
                    cur = analysis.estimated_tss(assigned[d][0])
                    assigned[d] = (
                        _scaled_endurance_capped(ftp, cur + leftover / len(easy_days), _FRIDAY_CAP_S),
                        WorkoutType.ENDURANCE,
                    )
            # Ondulação (rev. 3): só o "dia grande" da semana ganha a extensão
            # Z2; o outro dia de qualidade fica seco. Alterna ter ↔ qui.
            leftover = wk.planned_tss - _delivered()
            if leftover > _ABSORB_MIN_TSS and quality_days:
                big = sorted(quality_days)[i % len(quality_days)]
                w, wtype = assigned[big]
                assigned[big] = (_pad_with_z2(w, leftover, _MIDWEEK_CAP_S), wtype)
            leftover = wk.planned_tss - _delivered()
            if leftover > 0 and long_day is not None:
                cur = analysis.estimated_tss(assigned[long_day][0])
                assigned[long_day] = (
                    _long_for_tss(wk.block_type, ftp, cur + leftover, week_i=i),
                    WorkoutType.ENDURANCE,
                )
            dropped_total += max(0.0, wk.planned_tss - _delivered())
        elif recovery_week:
            # Deload entrega o alvo (~60%): os dias de Z2 escalam até 3h (rev. 2).
            flexers = easy_z2_days + short_days
            if flexers:
                target = max(0.0, wk.planned_tss - _delivered()) / len(flexers)
                for d in flexers:
                    assigned[d] = (_scaled_endurance_capped(ftp, target, _DELOAD_DAY_CAP_S),
                                   WorkoutType.ENDURANCE)
        else:
            # TAPER: dias de Z2 curtos, sem escalar — leveza é o objetivo.
            for d in short_days:
                assigned[d] = (_scaled_endurance_capped(ftp, 0.0, _SHORT_Z2_CAP_S),
                               WorkoutType.ENDURANCE)
            for d in easy_z2_days:
                assigned[d] = (templates.endurance(ftp), WorkoutType.ENDURANCE)

        for d in sorted(assigned):
            w, wtype = assigned[d]
            out.append(_daily_from(d, _with_meta(w, ftp), wtype))

        if not recovery_week:
            step += 1
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
        rest = max(1, min(3, 7 - int(profile.weekly_days)))

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

    days, tss_dropped = allocate_days(
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

    # Dias ocupados por OUTROS planos ativos: prova mais próxima vence o dia.
    others = (await session.execute(
        select(TrainingPlan).where(
            TrainingPlan.athlete_id == athlete_id,
            TrainingPlan.id != plan_id,
            TrainingPlan.deleted_at.is_(None),
        )
    )).scalars().all()
    conflict: dict = {}
    if others:
        by_id = {p.id: p for p in others}
        rows = (await session.execute(
            select(WorkoutPlanned).where(
                WorkoutPlanned.athlete_id == athlete_id,
                WorkoutPlanned.source_plan_id.in_(list(by_id)),
                WorkoutPlanned.deleted_at.is_(None),
            )
        )).scalars().all()
        for r in rows:
            conflict[r.planned_date] = (r.id, by_id[r.source_plan_id].race_date)

    written = 0
    for d in days:
        hit = conflict.get(d.planned_date)
        if hit is not None:
            other_id, other_race = hit
            if other_race is not None and other_race < plan.race_date:
                continue  # o outro plano atende prova mais próxima: dia é dele
            await session.execute(
                delete(WorkoutPlanned).where(WorkoutPlanned.id == other_id)
            )
        session.add(WorkoutPlanned(
            athlete_id=athlete_id, created_by=athlete_id,
            planned_date=d.planned_date, name=d.structure.get("name", "Treino"),
            workout_type=d.workout_type, planned_duration_s=d.planned_duration_s,
            planned_tss=d.planned_tss, structure=d.structure, description=d.description,
            source_plan_id=plan_id,
        ))
        written += 1
    await session.flush()
    return {
        "days": written,
        "tss_total": round(sum(d.planned_tss for d in days), 1),
        "tss_dropped": tss_dropped,
        "start": str(min((d.planned_date for d in days), default=today)),
        "end": str(max((d.planned_date for d in days), default=today)),
    }
