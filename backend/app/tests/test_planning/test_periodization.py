"""Tests for the deterministic periodization planner."""
from __future__ import annotations

from app.models.enums import BlockType
from app.services.planning.periodization import (
    RAMP_HARD_CAP,
    build_plan,
    summarize,
)


def test_plan_length_matches_weeks_to_race():
    plan = build_plan(current_ctl=60, weeks_to_race=12)
    assert len(plan) == 12
    assert plan[0].week_index == 1
    assert plan[-1].weeks_to_race == 0  # last week is race week


def test_block_sequence_is_ordered_base_build_peak_taper():
    plan = build_plan(current_ctl=60, weeks_to_race=16)
    # Map non-recovery weeks to their block, ignoring deload weeks.
    seq = [w.block_type for w in plan if w.block_type != BlockType.RECOVERY]
    order = {BlockType.BASE: 0, BlockType.BUILD: 1, BlockType.PEAK: 2, BlockType.TAPER: 3}
    ranks = [order[b] for b in seq]
    assert ranks == sorted(ranks)  # never goes backwards


def test_taper_is_present_and_reduces_load_for_priority_a():
    plan = build_plan(current_ctl=70, weeks_to_race=12, priority="A")
    taper_weeks = [w for w in plan if w.block_type == BlockType.TAPER]
    assert taper_weeks, "an A race must have a taper"
    pre_taper = [w for w in plan if w.block_type != BlockType.TAPER][-1]
    # Race-week load is well below the last build/peak load.
    assert plan[-1].planned_weekly_tss < pre_taper.planned_weekly_tss


def test_loading_weeks_never_exceed_10pct_increase():
    # The 10% cap governs progressive overload between *loading* weeks. Recovery
    # (deload) weeks intentionally drop load, and returning to a previously
    # handled load afterwards is not aggressive overload — so we exclude them.
    plan = build_plan(current_ctl=50, weeks_to_race=20)
    loads = [w.planned_weekly_tss for w in plan if not w.is_recovery_week]
    for prev, cur in zip(loads, loads[1:]):
        if cur > prev:  # only check increases
            assert (cur - prev) / prev <= RAMP_HARD_CAP + 1e-9


def test_has_recovery_deload_weeks_in_long_plan():
    plan = build_plan(current_ctl=60, weeks_to_race=20)
    assert any(w.is_recovery_week for w in plan)
    # Deload weeks drop load versus the preceding week.
    for i, w in enumerate(plan):
        if w.is_recovery_week and i > 0:
            assert w.planned_weekly_tss < plan[i - 1].planned_weekly_tss


def test_short_window_still_produces_a_plan():
    plan = build_plan(current_ctl=40, weeks_to_race=2)
    assert len(plan) == 2


def test_zero_or_negative_window_is_empty():
    assert build_plan(60, 0) == []


def test_summarize_reports_totals_by_block():
    plan = build_plan(current_ctl=60, weeks_to_race=12)
    s = summarize(plan)
    assert s["total_weeks"] == 12
    assert s["total_tss"] > 0
    assert "BASE" in s["tss_by_block"]
