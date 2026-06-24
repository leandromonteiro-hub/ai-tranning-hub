"""Tests for data_richness — TDD (red → green).

All inputs are synthetic (no real athlete data).
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.analysis.data_richness import RichnessIndex, compute_richness


# ---------------------------------------------------------------------------
# Helpers — synthetic builders
# ---------------------------------------------------------------------------


def _w(
    avg_power: float | None = None,
    avg_hr: float | None = None,
    completed: bool = True,
) -> Any:
    """Duck-typed workout-like object."""
    return SimpleNamespace(avg_power=avg_power, avg_hr=avg_hr, completed=completed)


def _r(
    hrv_ms: float | None = None,
    sleep_hours: float | None = None,
) -> Any:
    """Duck-typed recovery-day-like object."""
    return SimpleNamespace(hrv_ms=hrv_ms, sleep_hours=sleep_hours)


# ---------------------------------------------------------------------------
# Empty inputs
# ---------------------------------------------------------------------------


class TestEmptyInputs:
    def test_no_error_on_all_empty(self) -> None:
        result = compute_richness([], [], None, None)
        assert isinstance(result, RichnessIndex)

    def test_score_is_zero_on_all_empty(self) -> None:
        result = compute_richness([], [], None, None)
        assert result.score == pytest.approx(0.0)

    def test_label_is_baixa_on_all_empty(self) -> None:
        result = compute_richness([], [], None, None)
        assert result.label == "baixa"

    def test_n_workouts_zero_on_empty(self) -> None:
        result = compute_richness([], [], None, None)
        assert result.n_workouts == 0

    def test_years_covered_zero_on_missing_dates(self) -> None:
        result = compute_richness([], [], None, None)
        assert result.years_covered == pytest.approx(0.0)

    def test_all_pcts_zero_on_empty(self) -> None:
        result = compute_richness([], [], None, None)
        assert result.pct_power == pytest.approx(0.0)
        assert result.pct_hr == pytest.approx(0.0)
        assert result.pct_hrv == pytest.approx(0.0)
        assert result.pct_sleep == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Percentage computations
# ---------------------------------------------------------------------------


class TestPercentageComputations:
    def test_pct_power_100_when_all_have_power(self) -> None:
        workouts = [_w(avg_power=200.0), _w(avg_power=250.0)]
        result = compute_richness(workouts, [], None, None)
        assert result.pct_power == pytest.approx(100.0)

    def test_pct_power_50_when_half_have_power(self) -> None:
        workouts = [_w(avg_power=200.0), _w(avg_power=None)]
        result = compute_richness(workouts, [], None, None)
        assert result.pct_power == pytest.approx(50.0)

    def test_pct_power_0_when_none_have_power(self) -> None:
        workouts = [_w(avg_power=None), _w(avg_power=None)]
        result = compute_richness(workouts, [], None, None)
        assert result.pct_power == pytest.approx(0.0)

    def test_pct_hr_100_when_all_have_hr(self) -> None:
        workouts = [_w(avg_hr=140.0), _w(avg_hr=150.0)]
        result = compute_richness(workouts, [], None, None)
        assert result.pct_hr == pytest.approx(100.0)

    def test_pct_hr_0_when_none_have_hr(self) -> None:
        workouts = [_w(avg_hr=None)]
        result = compute_richness(workouts, [], None, None)
        assert result.pct_hr == pytest.approx(0.0)

    def test_pct_hrv_100_when_all_recovery_have_hrv(self) -> None:
        recovery = [_r(hrv_ms=45.0), _r(hrv_ms=50.0)]
        result = compute_richness([], recovery, None, None)
        assert result.pct_hrv == pytest.approx(100.0)

    def test_pct_hrv_50_when_half_have_hrv(self) -> None:
        recovery = [_r(hrv_ms=45.0), _r(hrv_ms=None)]
        result = compute_richness([], recovery, None, None)
        assert result.pct_hrv == pytest.approx(50.0)

    def test_pct_sleep_100_when_all_have_sleep(self) -> None:
        recovery = [_r(sleep_hours=7.5), _r(sleep_hours=8.0)]
        result = compute_richness([], recovery, None, None)
        assert result.pct_sleep == pytest.approx(100.0)

    def test_pct_sleep_0_when_none_have_sleep(self) -> None:
        recovery = [_r(sleep_hours=None)]
        result = compute_richness([], recovery, None, None)
        assert result.pct_sleep == pytest.approx(0.0)

    def test_pct_is_0_to_100_not_0_to_1(self) -> None:
        """Percentages must be on the 0–100 scale, not 0–1."""
        workouts = [_w(avg_power=200.0)]
        result = compute_richness(workouts, [], None, None)
        assert result.pct_power > 1.0  # not a fraction

    def test_pct_only_completed_workouts_counted_for_power(self) -> None:
        """Only completed workouts enter the pct_power denominator."""
        workouts = [
            _w(avg_power=200.0, completed=True),
            _w(avg_power=None, completed=False),  # not completed → not counted
        ]
        result = compute_richness(workouts, [], None, None)
        # 1 completed workout, 1 with power → 100 %
        assert result.pct_power == pytest.approx(100.0)

    def test_pct_exact_one_third(self) -> None:
        workouts = [_w(avg_power=200.0), _w(avg_power=None), _w(avg_power=None)]
        result = compute_richness(workouts, [], None, None)
        assert result.pct_power == pytest.approx(100.0 / 3.0, rel=1e-4)


# ---------------------------------------------------------------------------
# years_covered
# ---------------------------------------------------------------------------


class TestYearsCovered:
    def test_years_covered_two_years(self) -> None:
        start = date(2022, 1, 1)
        end = date(2024, 1, 1)
        result = compute_richness([], [], start, end)
        expected = (end - start).days / 365.25
        assert result.years_covered == pytest.approx(expected, rel=1e-4)

    def test_years_covered_zero_when_start_missing(self) -> None:
        result = compute_richness([], [], None, date(2024, 1, 1))
        assert result.years_covered == pytest.approx(0.0)

    def test_years_covered_zero_when_end_missing(self) -> None:
        result = compute_richness([], [], date(2022, 1, 1), None)
        assert result.years_covered == pytest.approx(0.0)

    def test_years_covered_three_months(self) -> None:
        start = date(2024, 1, 1)
        end = date(2024, 4, 1)
        result = compute_richness([], [], start, end)
        expected = (end - start).days / 365.25
        assert result.years_covered == pytest.approx(expected, rel=1e-4)
        assert result.years_covered < 0.5


# ---------------------------------------------------------------------------
# Score and label
# ---------------------------------------------------------------------------


class TestScoreAndLabel:
    def test_score_in_0_to_1(self) -> None:
        workouts = [_w(avg_power=200.0), _w(avg_power=250.0)]
        recovery = [_r(hrv_ms=45.0), _r(sleep_hours=7.5)]
        result = compute_richness(
            workouts, recovery, date(2022, 1, 1), date(2024, 1, 1)
        )
        assert 0.0 <= result.score <= 1.0

    def test_score_never_exceeds_1(self) -> None:
        # All perfect: 300 workouts, 100 % power/hr, 2+ years, 100 % hrv/sleep
        workouts = [_w(avg_power=200.0, avg_hr=140.0) for _ in range(300)]
        recovery = [_r(hrv_ms=45.0, sleep_hours=7.5) for _ in range(100)]
        result = compute_richness(
            workouts, recovery, date(2022, 1, 1), date(2024, 6, 1)
        )
        assert result.score <= 1.0

    def test_rich_athlete_alta(self) -> None:
        """2 years, 300 workouts, 95 % power, 100 % HRV/sleep → 'alta'."""
        n = 300
        power_with = int(n * 0.95)
        workouts = [_w(avg_power=200.0, avg_hr=140.0) for _ in range(power_with)] + [
            _w(avg_power=None, avg_hr=140.0) for _ in range(n - power_with)
        ]
        recovery = [_r(hrv_ms=45.0, sleep_hours=7.5) for _ in range(120)]
        result = compute_richness(
            workouts, recovery, date(2022, 1, 1), date(2024, 1, 1)
        )
        assert result.label == "alta"
        assert result.score >= 0.7

    def test_sparse_athlete_baixa(self) -> None:
        """3 months, 10 workouts, 0 % power/hrv → 'baixa'."""
        workouts = [_w(avg_power=None, avg_hr=None) for _ in range(10)]
        recovery = [_r(hrv_ms=None, sleep_hours=None) for _ in range(10)]
        result = compute_richness(
            workouts, recovery, date(2024, 1, 1), date(2024, 4, 1)
        )
        assert result.label == "baixa"
        assert result.score < 0.4

    def test_medium_athlete_media(self) -> None:
        """Moderate data: 1 year, 100 workouts, 60 % power, 60 % HRV → 'média'."""
        n = 100
        power_with = 60
        workouts = [_w(avg_power=200.0, avg_hr=140.0) for _ in range(power_with)] + [
            _w(avg_power=None, avg_hr=None) for _ in range(n - power_with)
        ]
        recovery = [_r(hrv_ms=45.0, sleep_hours=7.5) for _ in range(30)] + [
            _r(hrv_ms=None, sleep_hours=None) for _ in range(20)
        ]
        result = compute_richness(
            workouts, recovery, date(2023, 1, 1), date(2024, 1, 1)
        )
        assert result.label == "média"
        assert 0.4 <= result.score < 0.7

    def test_label_baixa_threshold(self) -> None:
        """Score just below 0.4 → 'baixa'."""
        # Only 5 workouts with no power/hr, 1 month period
        workouts = [_w(avg_power=None, avg_hr=None) for _ in range(5)]
        result = compute_richness(workouts, [], date(2024, 1, 1), date(2024, 2, 1))
        assert result.label == "baixa"

    def test_label_alta_threshold(self) -> None:
        """Score ≥ 0.7 → 'alta'."""
        # Very rich: 2+ years, 300 workouts, 100% power+hr+hrv+sleep
        workouts = [_w(avg_power=250.0, avg_hr=145.0) for _ in range(300)]
        recovery = [_r(hrv_ms=50.0, sleep_hours=8.0) for _ in range(150)]
        result = compute_richness(
            workouts, recovery, date(2022, 1, 1), date(2024, 6, 1)
        )
        assert result.label == "alta"

    def test_dataclass_fields_present(self) -> None:
        result = compute_richness([], [], None, None)
        assert hasattr(result, "years_covered")
        assert hasattr(result, "n_workouts")
        assert hasattr(result, "pct_power")
        assert hasattr(result, "pct_hr")
        assert hasattr(result, "pct_hrv")
        assert hasattr(result, "pct_sleep")
        assert hasattr(result, "score")
        assert hasattr(result, "label")

    def test_n_workouts_correct(self) -> None:
        workouts = [_w() for _ in range(42)]
        result = compute_richness(workouts, [], None, None)
        assert result.n_workouts == 42


# ---------------------------------------------------------------------------
# Exact-value regression — pins the formula against silent weight drift
# ---------------------------------------------------------------------------


class TestExactScoreRegression:
    def test_fully_rich_scores_exactly_one(self) -> None:
        """≈2 yrs, 300 completed workouts, 100% power/hrv/sleep → score == 1.0.

        Components: history 1.0*0.25 + power 1.0*0.30 + hrv 1.0*0.20
                    + count 1.0*0.15 + sleep 1.0*0.10 = 1.00
        """
        workouts = [_w(avg_power=200.0, avg_hr=140.0) for _ in range(300)]
        recovery = [_r(hrv_ms=45.0, sleep_hours=7.5) for _ in range(100)]
        result = compute_richness(
            workouts, recovery, date(2022, 1, 1), date(2024, 6, 1)
        )
        assert result.score == pytest.approx(1.0)
        assert result.label == "alta"

    def test_partial_hand_computed_score(self) -> None:
        """Hand-computed partial case asserted to abs=1e-4.

        Period > 2 yrs              → history_component = 1.0  → 0.25 * 1.0 = 0.25
        60% of completed have power → power_component   = 0.6  → 0.30 * 0.6 = 0.18
        0% recovery have hrv        → hrv_component     = 0.0  → 0.20 * 0.0 = 0.00
        150 completed workouts      → count_component   = 0.5  → 0.15 * 0.5 = 0.075
        0% recovery have sleep      → sleep_component   = 0.0  → 0.10 * 0.0 = 0.00
        Expected score = 0.25 + 0.18 + 0.00 + 0.075 + 0.00 = 0.505
        """
        # 150 completed workouts, 90 with power (60%), 60 without
        workouts = [_w(avg_power=200.0) for _ in range(90)] + [
            _w(avg_power=None) for _ in range(60)
        ]
        recovery = [_r(hrv_ms=None, sleep_hours=None) for _ in range(20)]
        result = compute_richness(
            workouts, recovery, date(2022, 1, 1), date(2024, 6, 1)
        )
        assert result.pct_power == pytest.approx(60.0)
        assert result.score == pytest.approx(0.505, abs=1e-4)
        assert result.label == "média"


# ---------------------------------------------------------------------------
# Boundary-pinned label tests — protect the threshold constants
# ---------------------------------------------------------------------------


class TestLabelBoundaries:
    """Engineer scores straddling 0.40 and 0.70 and assert the label flips.

    Period > 2 yrs is used throughout so history_component == 1.0 exactly
    (contributes 0.25), keeping the other components easy to reason about.
    """

    # --- 0.40 boundary: baixa ↔ média --------------------------------------

    def test_just_below_040_is_baixa(self) -> None:
        """Score engineered just under 0.40 → 'baixa'.

        history 1.0*0.25                       = 0.25
        30 completed, 12 power (40%) 0.30*0.40  = 0.12
        count 30/300=0.1 * 0.15                 = 0.015
        Expected = 0.385  (< 0.40)
        """
        workouts = [_w(avg_power=200.0) for _ in range(12)] + [
            _w(avg_power=None) for _ in range(18)
        ]
        result = compute_richness(
            workouts, [], date(2022, 1, 1), date(2024, 6, 1)
        )
        assert result.score == pytest.approx(0.385, abs=1e-4)
        assert result.label == "baixa"

    def test_just_above_040_is_media(self) -> None:
        """Score engineered just over 0.40 → 'média'.

        history 1.0*0.25                       = 0.25
        30 completed, 15 power (50%) 0.30*0.50  = 0.15
        count 30/300=0.1 * 0.15                 = 0.015
        Expected = 0.415  (>= 0.40)
        """
        workouts = [_w(avg_power=200.0) for _ in range(15)] + [
            _w(avg_power=None) for _ in range(15)
        ]
        result = compute_richness(
            workouts, [], date(2022, 1, 1), date(2024, 6, 1)
        )
        assert result.score == pytest.approx(0.415, abs=1e-4)
        assert result.label == "média"

    # --- 0.70 boundary: média ↔ alta ---------------------------------------

    def test_just_below_070_is_media(self) -> None:
        # history 0.25 + power(100%) 0.30 + hrv(70%) 0.20*0.70 = 0.55 + 0.14 = 0.69
        # Keep completed count negligible-but-counted: 10 completed → 10/300≈0.033
        # adds 0.005 → 0.695, still < 0.70.
        workouts = [_w(avg_power=200.0) for _ in range(10)]
        recovery = [_r(hrv_ms=45.0) for _ in range(7)] + [
            _r(hrv_ms=None) for _ in range(3)
        ]
        result = compute_richness(
            workouts, recovery, date(2022, 1, 1), date(2024, 6, 1)
        )
        assert result.score < 0.70
        assert result.label == "média"

    def test_just_above_070_is_alta(self) -> None:
        # history 0.25 + power(100%) 0.30 + hrv(80%) 0.20*0.80 = 0.55 + 0.16 = 0.71
        workouts = [_w(avg_power=200.0) for _ in range(10)]
        recovery = [_r(hrv_ms=45.0) for _ in range(8)] + [
            _r(hrv_ms=None) for _ in range(2)
        ]
        result = compute_richness(
            workouts, recovery, date(2022, 1, 1), date(2024, 6, 1)
        )
        assert result.score >= 0.70
        assert result.label == "alta"


# ---------------------------------------------------------------------------
# Completed-workout count drives the workout component (fix 3)
# ---------------------------------------------------------------------------


class TestWorkoutCountUsesCompleted:
    def test_non_completed_workouts_do_not_inflate_score(self) -> None:
        """Many non-completed workouts must NOT raise the workout component.

        Athlete A: 10 completed workouts (no other signal).
        Athlete B: same 10 completed + 290 NON-completed workouts.
        The workout component (and thus the score) must be IDENTICAL.
        """
        completed_only = [_w(avg_power=None, completed=True) for _ in range(10)]
        with_noncompleted = completed_only + [
            _w(avg_power=None, completed=False) for _ in range(290)
        ]
        result_a = compute_richness(completed_only, [], None, None)
        result_b = compute_richness(with_noncompleted, [], None, None)
        # Score identical — non-completed workouts ignored by the count component
        assert result_b.score == pytest.approx(result_a.score)
        # n_workouts still reports the TOTAL supplied
        assert result_a.n_workouts == 10
        assert result_b.n_workouts == 300

    def test_completed_count_saturates_workout_component(self) -> None:
        """300 completed workouts saturate the 0.15 workout component."""
        workouts = [_w(avg_power=None, completed=True) for _ in range(300)]
        result = compute_richness(workouts, [], None, None)
        # Only the workout component is non-zero: 1.0 * 0.15 = 0.15
        assert result.score == pytest.approx(0.15, abs=1e-4)
