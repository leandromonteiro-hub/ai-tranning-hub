"""Tests for profile_metrics — TDD (red → green).

All inputs are synthetic (no real athlete data).
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.analysis.profile_metrics import (
    BestPowerMarks,
    DerivedZones,
    IntensityDistribution,
    MeasuredZones,
    ModalitySplit,
    PowerMark,
    SportShare,
    WeeklyVolumeTrend,
    WorkoutTypeShare,
    best_power_marks,
    intensity_distribution,
    modality_split,
    weekly_volume_trend,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic workout builders
# ---------------------------------------------------------------------------


def _w(
    workout_date: date | None = None,
    duration_s: int | None = 3600,
    tss: float | None = None,
    extra: dict | None = None,
    distance_m: float | None = None,
    workout_type: str = "ENDURANCE",
    sport: str = "cycling",
    intensity_factor: float | None = None,
) -> Any:
    """Build a duck-typed workout-like object."""
    return SimpleNamespace(
        workout_date=workout_date or date(2025, 1, 6),
        duration_s=duration_s,
        tss=tss,
        extra=extra,
        distance_m=distance_m,
        workout_type=workout_type,
        sport=sport,
        intensity_factor=intensity_factor,
    )


# ---------------------------------------------------------------------------
# weekly_volume_trend
# ---------------------------------------------------------------------------


class TestWeeklyVolumeTrend:
    def test_single_workout_single_week(self) -> None:
        workouts = [_w(workout_date=date(2025, 1, 6), duration_s=3600, tss=80.0, distance_m=40_000)]
        result = weekly_volume_trend(workouts)
        assert isinstance(result, WeeklyVolumeTrend)
        assert len(result.weeks) == 1
        wk = result.weeks[0]
        assert wk.hours == pytest.approx(1.0)
        assert wk.tss == pytest.approx(80.0)
        assert wk.distance_km == pytest.approx(40.0)
        assert wk.workout_count == 1
        # Only one week → no trend
        assert result.trend is None

    def test_uses_source_tss_over_tss(self) -> None:
        # source_tss in extra takes priority over the tss field
        w = _w(tss=50.0, extra={"source_tss": 90.0})
        result = weekly_volume_trend([w])
        assert result.weeks[0].tss == pytest.approx(90.0)

    def test_falls_back_to_tss_when_no_source_tss(self) -> None:
        w = _w(tss=70.0, extra={})
        result = weekly_volume_trend([w])
        assert result.weeks[0].tss == pytest.approx(70.0)

    def test_none_duration_treated_as_zero(self) -> None:
        w = _w(duration_s=None)
        result = weekly_volume_trend([w])
        assert result.weeks[0].hours == pytest.approx(0.0)

    def test_none_distance_treated_as_zero(self) -> None:
        w = _w(distance_m=None)
        result = weekly_volume_trend([w])
        assert result.weeks[0].distance_km == pytest.approx(0.0)

    def test_multiple_workouts_same_week_aggregated(self) -> None:
        w1 = _w(workout_date=date(2025, 1, 6), duration_s=3600, tss=80.0)
        w2 = _w(workout_date=date(2025, 1, 8), duration_s=7200, tss=120.0)
        result = weekly_volume_trend([w1, w2])
        # Both in ISO week 2025-W02
        assert len(result.weeks) == 1
        wk = result.weeks[0]
        assert wk.hours == pytest.approx(3.0)
        assert wk.tss == pytest.approx(200.0)
        assert wk.workout_count == 2

    def test_two_different_weeks_produces_two_entries(self) -> None:
        w1 = _w(workout_date=date(2025, 1, 6))   # ISO 2025-W02
        w2 = _w(workout_date=date(2025, 1, 13))  # ISO 2025-W03
        result = weekly_volume_trend([w1, w2])
        assert len(result.weeks) == 2

    def test_weeks_sorted_chronologically(self) -> None:
        w1 = _w(workout_date=date(2025, 1, 13))
        w2 = _w(workout_date=date(2025, 1, 6))
        result = weekly_volume_trend([w1, w2])
        assert result.weeks[0].iso_week < result.weeks[1].iso_week

    def test_trend_rising(self) -> None:
        # 4 weeks: first two low hours, last two high hours → rising
        workouts = [
            _w(workout_date=date(2025, 1, 6), duration_s=3600),   # W02
            _w(workout_date=date(2025, 1, 13), duration_s=3600),  # W03
            _w(workout_date=date(2025, 1, 20), duration_s=18000), # W04
            _w(workout_date=date(2025, 1, 27), duration_s=18000), # W05
        ]
        result = weekly_volume_trend(workouts)
        assert result.trend is not None
        assert result.trend.direction == "rising"

    def test_trend_falling(self) -> None:
        workouts = [
            _w(workout_date=date(2025, 1, 6), duration_s=18000),  # W02
            _w(workout_date=date(2025, 1, 13), duration_s=18000), # W03
            _w(workout_date=date(2025, 1, 20), duration_s=3600),  # W04
            _w(workout_date=date(2025, 1, 27), duration_s=3600),  # W05
        ]
        result = weekly_volume_trend(workouts)
        assert result.trend is not None
        assert result.trend.direction == "falling"

    def test_trend_stable_when_change_below_5pct(self) -> None:
        # All weeks same duration → strictly stable
        workouts = [
            _w(workout_date=date(2025, 1, 6), duration_s=7200),
            _w(workout_date=date(2025, 1, 13), duration_s=7200),
            _w(workout_date=date(2025, 1, 20), duration_s=7200),
            _w(workout_date=date(2025, 1, 27), duration_s=7200),
        ]
        result = weekly_volume_trend(workouts)
        assert result.trend is not None
        assert result.trend.direction == "stable"

    def test_trend_has_sensible_mean_hours(self) -> None:
        # 2 h/week × 2 weeks
        workouts = [
            _w(workout_date=date(2025, 1, 6), duration_s=7200),
            _w(workout_date=date(2025, 1, 13), duration_s=7200),
        ]
        result = weekly_volume_trend(workouts)
        assert result.trend is not None
        assert result.trend.mean_hours == pytest.approx(2.0)
        assert result.trend.weeks_analysed == 2

    def test_empty_input(self) -> None:
        result = weekly_volume_trend([])
        assert result.weeks == []
        assert result.trend is None

    def test_iso_week_fields_correct(self) -> None:
        w = _w(workout_date=date(2025, 1, 1))  # ISO 2025-W01
        result = weekly_volume_trend([w])
        assert result.weeks[0].iso_year == 2025
        assert result.weeks[0].iso_week == 1


# ---------------------------------------------------------------------------
# modality_split
# ---------------------------------------------------------------------------


class TestModalitySplit:
    def test_single_cycling_workout(self) -> None:
        workouts = [_w(sport="cycling", workout_type="ENDURANCE", duration_s=3600)]
        result = modality_split(workouts)
        assert isinstance(result, ModalitySplit)
        assert result.total_workouts == 1
        assert len(result.by_sport) == 1
        assert result.by_sport[0].sport == "cycling"
        assert result.by_sport[0].pct_workouts == pytest.approx(1.0)
        assert result.by_sport[0].pct_hours == pytest.approx(1.0)

    def test_mixed_sports(self) -> None:
        workouts = [
            _w(sport="cycling", workout_type="ENDURANCE", duration_s=3600),
            _w(sport="swimming", workout_type="ENDURANCE", duration_s=3600),
            _w(sport="strength", workout_type="OTHER", duration_s=3600),
        ]
        result = modality_split(workouts)
        sports = {s.sport for s in result.by_sport}
        assert "cycling" in sports
        assert "swim" in sports
        assert "strength" in sports
        assert result.total_workouts == 3

    def test_pct_workouts_sum_to_one(self) -> None:
        workouts = [
            _w(sport="cycling", duration_s=3600),
            _w(sport="cycling", duration_s=3600),
            _w(sport="swimming", duration_s=3600),
        ]
        result = modality_split(workouts)
        total_pct = sum(s.pct_workouts for s in result.by_sport)
        assert total_pct == pytest.approx(1.0, abs=1e-6)

    def test_pct_hours_sum_to_one(self) -> None:
        workouts = [
            _w(sport="cycling", duration_s=3600),
            _w(sport="swimming", duration_s=7200),
        ]
        result = modality_split(workouts)
        total_pct = sum(s.pct_hours for s in result.by_sport)
        assert total_pct == pytest.approx(1.0, abs=1e-6)

    def test_by_workout_type_pct_sum_to_one(self) -> None:
        workouts = [
            _w(workout_type="ENDURANCE", duration_s=7200),
            _w(workout_type="THRESHOLD", duration_s=3600),
        ]
        result = modality_split(workouts)
        total_pct = sum(t.pct_workouts for t in result.by_workout_type)
        assert total_pct == pytest.approx(1.0, abs=1e-6)

    def test_none_duration_treated_as_zero_hours(self) -> None:
        workouts = [_w(duration_s=None, sport="cycling")]
        result = modality_split(workouts)
        assert result.by_sport[0].total_hours == pytest.approx(0.0)

    def test_sorted_by_count_descending(self) -> None:
        workouts = [
            _w(sport="swimming"),
            _w(sport="cycling"),
            _w(sport="cycling"),
        ]
        result = modality_split(workouts)
        assert result.by_sport[0].sport == "cycling"  # 2 workouts first

    def test_bike_normalised_to_cycling(self) -> None:
        workouts = [_w(sport="Bike")]
        result = modality_split(workouts)
        assert result.by_sport[0].sport == "cycling"

    def test_mtb_normalised_to_cycling(self) -> None:
        workouts = [_w(sport="MTB")]
        result = modality_split(workouts)
        assert result.by_sport[0].sport == "cycling"

    def test_empty_input(self) -> None:
        result = modality_split([])
        assert result.total_workouts == 1  # denominator protection
        assert result.by_sport == []
        assert result.by_workout_type == []

    def test_workout_type_enum_string(self) -> None:
        # WorkoutType.ENDURANCE as a string like "WorkoutType.ENDURANCE"
        workouts = [_w(workout_type="WorkoutType.ENDURANCE")]
        result = modality_split(workouts)
        assert result.by_workout_type[0].workout_type == "ENDURANCE"


# ---------------------------------------------------------------------------
# intensity_distribution
# ---------------------------------------------------------------------------


class TestIntensityDistribution:
    def test_returns_correct_types(self) -> None:
        result = intensity_distribution([])
        assert isinstance(result, IntensityDistribution)
        assert isinstance(result.measured, MeasuredZones)
        assert isinstance(result.derived, DerivedZones)

    def test_measured_source_label(self) -> None:
        result = intensity_distribution([])
        assert result.measured.source == "trainingpeaks"

    def test_derived_source_label(self) -> None:
        result = intensity_distribution([])
        assert result.derived.source == "derived_if"

    def test_measured_aggregates_pwr_zone_minutes(self) -> None:
        workouts = [
            _w(extra={"pwr_zone_minutes": [60, 30, 10, 5, 2, 0, 0, 0, 0, 0]}),
            _w(extra={"pwr_zone_minutes": [40, 20, 5, 0, 0, 0, 0, 0, 0, 0]}),
        ]
        result = intensity_distribution(workouts)
        m = result.measured
        assert m.pwr_zone_minutes[0] == 100  # 60 + 40
        assert m.pwr_zone_minutes[1] == 50   # 30 + 20
        assert m.pwr_zone_minutes[2] == 15   # 10 + 5
        assert m.workouts_with_power_zones == 2

    def test_measured_aggregates_hr_zone_minutes(self) -> None:
        workouts = [
            _w(extra={"hr_zone_minutes": [10, 20, 30, 5, 0]}),
        ]
        result = intensity_distribution(workouts)
        m = result.measured
        assert m.hr_zone_minutes[0] == 10
        assert m.hr_zone_minutes[2] == 30
        assert m.workouts_with_hr_zones == 1

    def test_measured_no_zone_data_stays_zero(self) -> None:
        workouts = [_w(extra={}), _w(extra=None)]
        result = intensity_distribution(workouts)
        m = result.measured
        assert all(v == 0 for v in m.pwr_zone_minutes)
        assert all(v == 0 for v in m.hr_zone_minutes)
        assert m.workouts_with_power_zones == 0

    def test_derived_z1_for_low_if(self) -> None:
        # IF=0.60 → Z1
        workouts = [_w(intensity_factor=0.60, duration_s=3600)]
        result = intensity_distribution(workouts)
        d = result.derived
        assert d.z1_hours == pytest.approx(1.0)
        assert d.z2_hours == pytest.approx(0.0)
        assert d.z3_hours == pytest.approx(0.0)

    def test_derived_z2_for_threshold_if(self) -> None:
        # IF=0.82 → Z2
        workouts = [_w(intensity_factor=0.82, duration_s=3600)]
        result = intensity_distribution(workouts)
        d = result.derived
        assert d.z2_hours == pytest.approx(1.0)

    def test_derived_z3_for_high_if(self) -> None:
        # IF=0.95 → Z3
        workouts = [_w(intensity_factor=0.95, duration_s=3600)]
        result = intensity_distribution(workouts)
        d = result.derived
        assert d.z3_hours == pytest.approx(1.0)

    def test_derived_none_if_unclassified(self) -> None:
        workouts = [_w(intensity_factor=None, duration_s=7200)]
        result = intensity_distribution(workouts)
        d = result.derived
        assert d.unclassified_hours == pytest.approx(2.0)
        assert d.workouts_classified == 0

    def test_derived_pct_sum_to_one_when_all_classified(self) -> None:
        workouts = [
            _w(intensity_factor=0.60, duration_s=3600),
            _w(intensity_factor=0.80, duration_s=3600),
            _w(intensity_factor=0.95, duration_s=3600),
        ]
        result = intensity_distribution(workouts)
        d = result.derived
        # Percentages are rounded to 4 decimal places; allow ±0.001 tolerance
        assert d.z1_pct + d.z2_pct + d.z3_pct == pytest.approx(1.0, abs=1e-3)

    def test_polarized_distribution(self) -> None:
        # 80 % Z1, 5 % Z2, 15 % Z3 → polarized
        workouts = [
            _w(intensity_factor=0.60, duration_s=int(0.80 * 3600)),
            _w(intensity_factor=0.82, duration_s=int(0.05 * 3600)),
            _w(intensity_factor=0.95, duration_s=int(0.15 * 3600)),
        ]
        result = intensity_distribution(workouts)
        assert result.derived.distribution_label == "polarized"

    def test_sweet_spot_distribution(self) -> None:
        # 30 % Z1, 50 % Z2, 20 % Z3 → sweet_spot (Z2 ≥ 35 %)
        workouts = [
            _w(intensity_factor=0.60, duration_s=int(0.30 * 3600)),
            _w(intensity_factor=0.82, duration_s=int(0.50 * 3600)),
            _w(intensity_factor=0.95, duration_s=int(0.20 * 3600)),
        ]
        result = intensity_distribution(workouts)
        assert result.derived.distribution_label == "sweet_spot"

    def test_pyramidal_distribution(self) -> None:
        # 60 % Z1, 30 % Z2, 10 % Z3 → pyramidal (Z1 > Z2 > Z3, not polarized, Z2 < 35 %)
        workouts = [
            _w(intensity_factor=0.60, duration_s=int(0.60 * 3600)),
            _w(intensity_factor=0.82, duration_s=int(0.30 * 3600)),
            _w(intensity_factor=0.95, duration_s=int(0.10 * 3600)),
        ]
        result = intensity_distribution(workouts)
        assert result.derived.distribution_label == "pyramidal"

    def test_empty_input_gives_mixed_label(self) -> None:
        result = intensity_distribution([])
        assert result.derived.distribution_label == "mixed"

    def test_boundary_if_075_is_z2(self) -> None:
        # IF exactly at boundary 0.75 → Z2 (0.75 ≤ IF < 0.90)
        workouts = [_w(intensity_factor=0.75, duration_s=3600)]
        result = intensity_distribution(workouts)
        assert result.derived.z2_hours == pytest.approx(1.0)

    def test_boundary_if_090_is_z3(self) -> None:
        # IF exactly at 0.90 → Z3 (IF ≥ 0.90)
        workouts = [_w(intensity_factor=0.90, duration_s=3600)]
        result = intensity_distribution(workouts)
        assert result.derived.z3_hours == pytest.approx(1.0)

    def test_pwr_zone_minutes_list_truncated_at_10(self) -> None:
        # TP may return fewer zones; extra elements should be ignored gracefully
        workouts = [_w(extra={"pwr_zone_minutes": [10, 20, 30]})]
        result = intensity_distribution(workouts)
        assert result.measured.pwr_zone_minutes[0] == 10
        assert result.measured.pwr_zone_minutes[3] == 0  # not present


# ---------------------------------------------------------------------------
# best_power_marks
# ---------------------------------------------------------------------------


class TestBestPowerMarks:
    def test_standard_durations_present(self) -> None:
        curve = {5: 1200.0, 60: 900.0, 300: 450.0, 1200: 350.0, 3600: 280.0}
        result = best_power_marks(curve)
        durations = [m.duration_s for m in result.marks]
        assert 5 in durations
        assert 60 in durations
        assert 300 in durations
        assert 1200 in durations
        assert 3600 in durations

    def test_marks_in_ascending_duration_order(self) -> None:
        curve = {5: 1200.0, 60: 900.0, 300: 450.0, 1200: 350.0, 3600: 280.0}
        result = best_power_marks(curve)
        durations = [m.duration_s for m in result.marks]
        assert durations == sorted(durations)

    def test_w_per_kg_computed_when_weight_given(self) -> None:
        curve = {300: 300.0}
        result = best_power_marks(curve, weight_kg=75.0)
        mark = result.marks[0]
        assert mark.w_per_kg == pytest.approx(4.0)

    def test_w_per_kg_none_when_no_weight(self) -> None:
        curve = {300: 300.0}
        result = best_power_marks(curve, weight_kg=None)
        assert result.marks[0].w_per_kg is None

    def test_missing_duration_not_included(self) -> None:
        # Only 300 s in curve — 5s, 60s, 1200s, 3600s should be absent
        curve = {300: 450.0}
        result = best_power_marks(curve)
        assert len(result.marks) == 1
        assert result.marks[0].duration_s == 300

    def test_empty_curve_returns_empty_marks(self) -> None:
        result = best_power_marks({})
        assert result.marks == []

    def test_watts_values_correct(self) -> None:
        curve = {5: 1200.0, 60: 900.0, 300: 450.0}
        result = best_power_marks(curve)
        watts_map = {m.duration_s: m.watts for m in result.marks}
        assert watts_map[5] == pytest.approx(1200.0)
        assert watts_map[60] == pytest.approx(900.0)
        assert watts_map[300] == pytest.approx(450.0)

    def test_weight_stored_on_result(self) -> None:
        result = best_power_marks({300: 300.0}, weight_kg=68.5)
        assert result.weight_kg == pytest.approx(68.5)

    def test_zero_weight_gives_none_w_per_kg(self) -> None:
        # weight_kg=0 would cause division by zero; should be treated as None
        curve = {300: 300.0}
        result = best_power_marks(curve, weight_kg=0.0)
        assert result.marks[0].w_per_kg is None

    def test_w_per_kg_precision(self) -> None:
        # 350 W / 70 kg = 5.0 W/kg exactly
        curve = {300: 350.0}
        result = best_power_marks(curve, weight_kg=70.0)
        assert result.marks[0].w_per_kg == pytest.approx(5.0)

    def test_extra_durations_in_curve_ignored(self) -> None:
        # Duration 120 is not in the standard list and should not appear
        curve = {5: 1200.0, 120: 700.0, 300: 450.0}
        result = best_power_marks(curve)
        durations = [m.duration_s for m in result.marks]
        assert 120 not in durations
        assert 5 in durations
        assert 300 in durations
