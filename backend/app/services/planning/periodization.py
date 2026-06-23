"""Deterministic periodization planner.

Given the current fitness (CTL) and the number of weeks until a target race, it
builds a week-by-week macrocycle (base -> build -> peak -> taper) with planned
weekly TSS. Pure and fully unit-tested. Hard invariant: weekly load never
increases by more than 10% versus the previous loading week (the non-negotiable
safety rule); recovery (deload) weeks and the taper reduce load deliberately.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import BlockType

# Tunable defaults (documented in docs/training_methodology.md / safety_rules.md).
RAMP_TARGET = 0.08          # aim for +8%/week on loading weeks
RAMP_HARD_CAP = 0.10        # never exceed +10%/week
DELOAD_EVERY = 4            # every 4th week is a recovery/deload week
DELOAD_FACTOR = 0.60        # deload weeks ~60% of the prior loading week
TAPER_FACTORS = [0.60, 0.45]  # taper weeks as fraction of pre-taper load (last = race week)


@dataclass
class PlannedWeek:
    week_index: int            # 1 = first week of the plan
    weeks_to_race: int         # 0 = race week
    block_type: BlockType
    planned_weekly_tss: float
    is_recovery_week: bool
    focus: str


def _allocate_phases(total_weeks: int, priority: str) -> dict[BlockType, int]:
    """Split the available weeks across base/build/peak/taper, working from race."""
    taper = 0 if total_weeks <= 1 else (1 if total_weeks <= 4 else 2)
    if priority in ("B", "C"):
        taper = min(taper, 1)
    peak = 0 if total_weeks <= 3 else max(1, round(total_weeks * 0.15))
    remaining = max(0, total_weeks - taper - peak)
    build = round(remaining * 0.5)
    base = remaining - build
    return {
        BlockType.BASE: base,
        BlockType.BUILD: build,
        BlockType.PEAK: peak,
        BlockType.TAPER: taper,
    }


_FOCUS = {
    BlockType.BASE: "Volume aeróbico (Z2), durabilidade, base de força",
    BlockType.BUILD: "Threshold e sweet spot, especificidade crescente",
    BlockType.PEAK: "VO2max e intensidade específica da prova, volume reduzido",
    BlockType.TAPER: "Redução de volume, manutenção de intensidade, frescor",
    BlockType.RECOVERY: "Recuperação ativa, deload",
}


def build_plan(
    current_ctl: float,
    weeks_to_race: int,
    priority: str = "A",
    baseline_weekly_tss: float | None = None,
) -> list[PlannedWeek]:
    """Return the week-by-week plan from now until the race (inclusive of race week)."""
    if weeks_to_race < 1:
        return []

    # Steady-state weekly TSS that sustains the current CTL is ~ CTL * 7.
    start_load = baseline_weekly_tss if baseline_weekly_tss else max(150.0, current_ctl * 7.0)

    phases = _allocate_phases(weeks_to_race, priority)
    # Ordered sequence of block types across the timeline (base -> ... -> taper).
    sequence: list[BlockType] = []
    for block in (BlockType.BASE, BlockType.BUILD, BlockType.PEAK, BlockType.TAPER):
        sequence.extend([block] * phases[block])
    # Safety net if rounding lost/gained a week.
    while len(sequence) < weeks_to_race:
        sequence.insert(0, BlockType.BASE)
    sequence = sequence[:weeks_to_race]

    weeks: list[PlannedWeek] = []
    prev_loading = start_load
    last_pre_taper_load = start_load
    load_week_counter = 0

    for i, block in enumerate(sequence):
        week_index = i + 1
        to_race = weeks_to_race - week_index  # 0 on race week

        if block == BlockType.TAPER:
            taper_pos = sum(1 for b in sequence[: i + 1] if b == BlockType.TAPER) - 1
            factor = TAPER_FACTORS[min(taper_pos, len(TAPER_FACTORS) - 1)]
            tss = round(last_pre_taper_load * factor, 1)
            weeks.append(PlannedWeek(week_index, to_race, block, tss, False, _FOCUS[block]))
            continue

        load_week_counter += 1
        is_deload = load_week_counter % DELOAD_EVERY == 0
        if is_deload:
            tss = round(prev_loading * DELOAD_FACTOR, 1)
            weeks.append(
                PlannedWeek(week_index, to_race, BlockType.RECOVERY, tss, True,
                            _FOCUS[BlockType.RECOVERY])
            )
            # Do not advance prev_loading on a deload; build resumes from it.
            continue

        if i == 0:
            tss = round(start_load, 1)
        else:
            # Progress by the target ramp, hard-capped at +10%.
            target = prev_loading * (1 + RAMP_TARGET)
            cap = prev_loading * (1 + RAMP_HARD_CAP)
            tss = round(min(target, cap), 1)
            # Peak weeks hold volume rather than growing it (intensity rises instead).
            if block == BlockType.PEAK:
                tss = round(prev_loading, 1)

        weeks.append(PlannedWeek(week_index, to_race, block, tss, False, _FOCUS[block]))
        prev_loading = tss
        last_pre_taper_load = tss

    return weeks


def summarize(weeks: list[PlannedWeek]) -> dict:
    """Aggregate totals per block for quick display / explanation."""
    by_block: dict[str, float] = {}
    for w in weeks:
        by_block[w.block_type.value] = round(by_block.get(w.block_type.value, 0.0) + w.planned_weekly_tss, 1)
    return {
        "total_weeks": len(weeks),
        "total_tss": round(sum(w.planned_weekly_tss for w in weeks), 1),
        "tss_by_block": by_block,
        "peak_weekly_tss": round(max((w.planned_weekly_tss for w in weeks), default=0.0), 1),
    }
