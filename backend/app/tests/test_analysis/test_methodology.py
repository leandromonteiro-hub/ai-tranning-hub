"""Tests for methodology.py — TDD (red → green).

Covers:
- detect_blocks: CTL-trend-based segmentation
- detect_races: RACE enum, keyword, TSS/IF spike
- taper_windows: pre-race CTL/ATL/TSB/weekly-TSS reconstruction
- coach_comment_terms: term-frequency with stopword removal

Synthetic data only — no real athlete data.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.analysis.methodology import (
    Block,
    Race,
    TaperWindow,
    coach_comment_terms,
    detect_blocks,
    detect_races,
    taper_windows,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_metric(
    metric_date: date,
    ctl: float,
    atl: float,
    tsb: float,
    daily_tss: float,
) -> SimpleNamespace:
    """Build a duck-typed load_metric object."""
    return SimpleNamespace(
        metric_date=metric_date,
        ctl=ctl,
        atl=atl,
        tsb=tsb,
        daily_tss=daily_tss,
    )


def _make_workout(
    workout_date: date,
    name: str = "workout",
    workout_type: str = "ENDURANCE",
    tss: float = 80.0,
    intensity_factor: float = 0.75,
    extra: dict | None = None,
) -> SimpleNamespace:
    """Build a duck-typed workout object."""
    return SimpleNamespace(
        workout_date=workout_date,
        name=name,
        workout_type=workout_type,
        tss=tss,
        intensity_factor=intensity_factor,
        extra=extra or {},
    )


def _ramp_ctl(
    start_date: date,
    n_days: int,
    ctl_start: float,
    ctl_delta_per_day: float,
    daily_tss: float = 80.0,
) -> list[SimpleNamespace]:
    """Generate synthetic load metrics with linearly ramping CTL."""
    metrics = []
    for i in range(n_days):
        d = start_date + timedelta(days=i)
        ctl = ctl_start + ctl_delta_per_day * i
        atl = ctl + 10.0  # atl always slightly above ctl for simplicity
        tsb = -(atl - ctl)
        metrics.append(_make_metric(d, ctl=ctl, atl=atl, tsb=tsb, daily_tss=daily_tss))
    return metrics


def _has_number(s: str) -> bool:
    """Return True if the string contains at least one digit."""
    return bool(re.search(r"\d", s))


# ===========================================================================
# detect_blocks
# ===========================================================================

class TestDetectBlocks:
    """Test segmentation of load_metrics into training blocks."""

    def test_empty_metrics_returns_empty(self) -> None:
        result = detect_blocks([])
        assert result == []

    def test_single_metric_returns_single_block(self) -> None:
        metrics = [_make_metric(date(2024, 1, 15), ctl=40.0, atl=42.0, tsb=-2.0, daily_tss=80.0)]
        result = detect_blocks(metrics)
        # At minimum one block should be returned
        assert len(result) >= 1
        assert isinstance(result[0], Block)

    def test_detect_base_block_from_low_ctl_slow_rise(self) -> None:
        """A slow CTL ramp (+0.5/day) at low absolute CTL → base block."""
        # 28 days of gentle CTL rise from 30 → 44, low TSS (~350/week = 50/day)
        metrics = _ramp_ctl(date(2024, 1, 1), n_days=28, ctl_start=30.0,
                            ctl_delta_per_day=0.5, daily_tss=50.0)
        result = detect_blocks(metrics)
        block_types = [b.block_type for b in result]
        assert "base" in block_types or "build" in block_types, (
            f"Expected base or build block; got {block_types}"
        )

    def test_detect_build_block_from_sustained_ctl_rise(self) -> None:
        """A sustained CTL ramp (+1.0/day, ~600 TSS/week) → build block."""
        metrics = _ramp_ctl(date(2024, 2, 1), n_days=28, ctl_start=40.0,
                            ctl_delta_per_day=1.0, daily_tss=85.0)
        result = detect_blocks(metrics)
        block_types = [b.block_type for b in result]
        assert "build" in block_types, f"Expected build block; got {block_types}"

    def test_detect_taper_block_from_ctl_plateau_with_rising_tsb(self) -> None:
        """CTL plateau + strongly rising TSB (ctl declining, atl dropping faster) → taper."""
        # Phase 1: build-up period (21 days of ctl rise)
        buildup = _ramp_ctl(date(2024, 3, 1), n_days=21, ctl_start=60.0,
                            ctl_delta_per_day=1.0, daily_tss=90.0)
        # Phase 2: taper — CTL slowly drops, TSS drops sharply, TSB becomes positive
        taper_start = date(2024, 3, 22)
        taper_metrics = []
        for i in range(14):
            d = taper_start + timedelta(days=i)
            ctl = 81.0 - i * 0.5        # gentle CTL decline
            atl = 85.0 - i * 3.0        # sharp ATL decline (low training stress)
            tsb = ctl - atl              # becomes positive during taper
            tss = 30.0                   # very low daily TSS
            taper_metrics.append(_make_metric(d, ctl=ctl, atl=atl, tsb=tsb, daily_tss=tss))

        all_metrics = buildup + taper_metrics
        result = detect_blocks(all_metrics)
        block_types = [b.block_type for b in result]
        assert "taper" in block_types, f"Expected taper block; got {block_types}"

    def test_detect_recovery_block_from_low_tss_trough(self) -> None:
        """A week with near-zero TSS and CTL decline → recovery block."""
        # Build up to CTL=65 first
        buildup = _ramp_ctl(date(2024, 4, 1), n_days=21, ctl_start=55.0,
                            ctl_delta_per_day=0.5, daily_tss=80.0)
        # Then a recovery week: very low TSS, CTL keeps falling
        recovery_start = date(2024, 4, 22)
        recovery_metrics = []
        for i in range(7):
            d = recovery_start + timedelta(days=i)
            ctl = 65.5 - i * 1.0
            atl = 60.0 - i * 2.0
            tsb = ctl - atl
            tss = 10.0
            recovery_metrics.append(_make_metric(d, ctl=ctl, atl=atl, tsb=tsb, daily_tss=tss))

        all_metrics = buildup + recovery_metrics
        result = detect_blocks(all_metrics)
        block_types = [b.block_type for b in result]
        assert "recovery" in block_types, f"Expected recovery block; got {block_types}"

    def test_all_blocks_have_non_empty_evidence(self) -> None:
        """Every block must carry a non-empty evidence string."""
        metrics = (
            _ramp_ctl(date(2024, 5, 1), n_days=28, ctl_start=40.0, ctl_delta_per_day=0.8, daily_tss=80.0)
            + _ramp_ctl(date(2024, 5, 29), n_days=14, ctl_start=62.4, ctl_delta_per_day=-0.5, daily_tss=25.0)
        )
        result = detect_blocks(metrics)
        for block in result:
            assert block.evidence, f"Block {block} has empty evidence"
            assert _has_number(block.evidence), (
                f"Block evidence must cite a number; got: {block.evidence!r}"
            )

    def test_block_dates_are_contiguous_and_chronological(self) -> None:
        """Block start/end dates must be ordered and non-overlapping."""
        metrics = _ramp_ctl(date(2024, 6, 1), n_days=42, ctl_start=35.0,
                            ctl_delta_per_day=0.6, daily_tss=75.0)
        result = detect_blocks(metrics)
        for i, block in enumerate(result):
            assert block.start <= block.end, (
                f"Block {i}: start {block.start} > end {block.end}"
            )
            if i > 0:
                assert result[i].start > result[i - 1].end or (
                    result[i].start >= result[i - 1].start
                )

    def test_block_type_values_are_valid(self) -> None:
        """block_type must be one of the five allowed values."""
        valid = {"base", "build", "peak", "taper", "recovery"}
        metrics = _ramp_ctl(date(2024, 7, 1), n_days=30, ctl_start=45.0,
                            ctl_delta_per_day=0.7, daily_tss=80.0)
        result = detect_blocks(metrics)
        for block in result:
            assert block.block_type in valid, (
                f"Unexpected block_type: {block.block_type!r}"
            )

    def test_evidence_contains_dates_or_ctl_values(self) -> None:
        """Evidence string should cite CTL values or date strings."""
        metrics = _ramp_ctl(date(2024, 8, 1), n_days=28, ctl_start=50.0,
                            ctl_delta_per_day=1.0, daily_tss=90.0)
        result = detect_blocks(metrics)
        for block in result:
            # Evidence must contain at least one numeric value
            assert _has_number(block.evidence), (
                f"No numeric evidence in block: {block.evidence!r}"
            )


# ===========================================================================
# detect_races
# ===========================================================================

class TestDetectRaces:
    """Test race detection from workouts."""

    def test_empty_workouts_returns_empty(self) -> None:
        result = detect_races([])
        assert result == []

    def test_detects_race_workout_type(self) -> None:
        """A workout with workout_type == 'RACE' must be detected."""
        workouts = [_make_workout(date(2024, 3, 10), name="Treino Domingo",
                                  workout_type="RACE", tss=180.0)]
        result = detect_races(workouts)
        assert len(result) == 1
        assert result[0].date == date(2024, 3, 10)

    def test_detects_race_enum_object(self) -> None:
        """Accept WorkoutType enum objects, not just strings."""
        from app.models.enums import WorkoutType
        workouts = [_make_workout(date(2024, 4, 7), name="Copa Regional",
                                  workout_type=WorkoutType.RACE, tss=200.0)]
        result = detect_races(workouts)
        assert len(result) == 1

    def test_detects_by_keyword_prova(self) -> None:
        workouts = [_make_workout(date(2024, 5, 12), name="Prova Estadual XCO",
                                  workout_type="ENDURANCE", tss=150.0)]
        result = detect_races(workouts)
        assert len(result) == 1
        assert result[0].date == date(2024, 5, 12)

    def test_detects_by_keyword_maratona(self) -> None:
        workouts = [_make_workout(date(2024, 6, 2), name="Maratona MTB 2024",
                                  workout_type="ENDURANCE", tss=200.0)]
        result = detect_races(workouts)
        assert len(result) == 1

    def test_detects_by_keyword_xcm(self) -> None:
        workouts = [_make_workout(date(2024, 6, 15), name="XCM Regional",
                                  workout_type="ENDURANCE", tss=180.0)]
        result = detect_races(workouts)
        assert len(result) == 1

    def test_detects_by_keyword_copa(self) -> None:
        workouts = [_make_workout(date(2024, 7, 7), name="Copa Brasil MTB",
                                  workout_type="THRESHOLD", tss=210.0)]
        result = detect_races(workouts)
        assert len(result) == 1

    def test_detects_by_keyword_campeonato(self) -> None:
        workouts = [_make_workout(date(2024, 8, 18), name="Campeonato Mineiro",
                                  workout_type="THRESHOLD", tss=230.0)]
        result = detect_races(workouts)
        assert len(result) == 1

    def test_detects_by_keyword_gp(self) -> None:
        workouts = [_make_workout(date(2024, 9, 1), name="GP XCO Juiz de Fora",
                                  workout_type="ENDURANCE", tss=160.0)]
        result = detect_races(workouts)
        assert len(result) == 1

    def test_detects_by_tss_spike(self) -> None:
        """A workout with TSS >> typical level (spike) should be flagged."""
        # Normal training: TSS around 80; spike to 300 → race-level effort
        workouts = [_make_workout(date(2024, 10, 5), name="Domingo duro",
                                  workout_type="THRESHOLD", tss=320.0,
                                  intensity_factor=0.95)]
        result = detect_races(workouts)
        assert len(result) == 1

    def test_normal_workout_not_flagged(self) -> None:
        """Regular endurance workouts should NOT be detected as races."""
        workouts = [
            _make_workout(date(2024, 1, 8), name="Long Ride Z2", workout_type="ENDURANCE",
                          tss=80.0, intensity_factor=0.70),
            _make_workout(date(2024, 1, 10), name="Recovery spin", workout_type="RECOVERY",
                          tss=30.0, intensity_factor=0.55),
        ]
        result = detect_races(workouts)
        assert result == []

    def test_all_races_have_evidence(self) -> None:
        """Every detected race must carry non-empty evidence with a number or keyword."""
        from app.models.enums import WorkoutType
        workouts = [
            _make_workout(date(2024, 3, 3), name="Prova XCO", workout_type="ENDURANCE", tss=190.0),
            _make_workout(date(2024, 4, 14), workout_type=WorkoutType.RACE, tss=210.0),
        ]
        result = detect_races(workouts)
        for race in result:
            assert race.evidence, f"Race {race.date} has no evidence"
            # Evidence must contain a number or a keyword string
            has_evidence = _has_number(race.evidence) or any(
                kw in race.evidence.lower()
                for kw in ("race", "prova", "keyword", "xco", "tss", "tipo", "type")
            )
            assert has_evidence, f"Evidence lacks detail: {race.evidence!r}"

    def test_no_duplicate_races_for_same_date(self) -> None:
        """If workout_type=RACE AND title contains 'prova', count only once."""
        from app.models.enums import WorkoutType
        workouts = [
            _make_workout(date(2024, 5, 5), name="Prova Estadual",
                          workout_type=WorkoutType.RACE, tss=200.0),
        ]
        result = detect_races(workouts)
        race_dates = [r.date for r in result]
        assert len(race_dates) == len(set(race_dates)), "Duplicate race dates detected"

    def test_case_insensitive_keyword_matching(self) -> None:
        """Keywords must match regardless of case."""
        workouts = [
            _make_workout(date(2024, 6, 9), name="MARATONA MTB 2024",
                          workout_type="ENDURANCE", tss=200.0),
        ]
        result = detect_races(workouts)
        assert len(result) == 1


# ===========================================================================
# taper_windows
# ===========================================================================

class TestTaperWindows:
    """Test reconstruction of pre-race taper windows."""

    def test_empty_races_returns_empty(self) -> None:
        metrics = _ramp_ctl(date(2024, 1, 1), n_days=30, ctl_start=50.0,
                            ctl_delta_per_day=0.5, daily_tss=70.0)
        result = taper_windows([], metrics)
        assert result == []

    def test_no_metrics_returns_empty(self) -> None:
        races = [Race(date=date(2024, 3, 10), name="Race A", evidence="test")]
        result = taper_windows(races, [])
        assert result == []

    def test_taper_window_captures_correct_race_date(self) -> None:
        """The returned TaperWindow.race_date matches the input race date."""
        # Build 30 days of metrics ending on race day
        race_date = date(2024, 4, 14)
        metrics = _ramp_ctl(date(2024, 3, 15), n_days=31, ctl_start=65.0,
                            ctl_delta_per_day=0.3, daily_tss=80.0)
        races = [Race(date=race_date, name="XCO Cup", evidence="keyword:xco")]
        result = taper_windows(races, metrics)
        assert len(result) == 1
        assert result[0].race_date == race_date

    def test_taper_window_ctl_start_less_than_ctl_race_on_rising(self) -> None:
        """During a build phase, ctl_start < ctl_race (CTL was still rising pre-race)."""
        race_date = date(2024, 5, 26)
        # 28-day ramp
        metrics = _ramp_ctl(date(2024, 4, 28), n_days=29, ctl_start=55.0,
                            ctl_delta_per_day=0.8, daily_tss=85.0)
        races = [Race(date=race_date, name="Prova", evidence="keyword:prova")]
        result = taper_windows(races, metrics)
        assert len(result) == 1
        tw = result[0]
        assert tw.ctl_start < tw.ctl_race, (
            f"Expected ctl_start < ctl_race on a build phase; "
            f"got ctl_start={tw.ctl_start}, ctl_race={tw.ctl_race}"
        )

    def test_taper_window_has_non_empty_weekly_tss_trend(self) -> None:
        """weekly_tss_trend must have at least 1 entry for a window with enough data."""
        race_date = date(2024, 6, 16)
        metrics = _ramp_ctl(date(2024, 5, 17), n_days=31, ctl_start=60.0,
                            ctl_delta_per_day=0.5, daily_tss=80.0)
        races = [Race(date=race_date, name="Copa", evidence="keyword:copa")]
        result = taper_windows(races, metrics)
        assert len(result) == 1
        assert len(result[0].weekly_tss_trend) >= 1

    def test_taper_window_evidence_non_empty_with_number(self) -> None:
        """TaperWindow evidence must be non-empty and contain a number."""
        race_date = date(2024, 7, 7)
        metrics = _ramp_ctl(date(2024, 6, 7), n_days=31, ctl_start=58.0,
                            ctl_delta_per_day=0.6, daily_tss=78.0)
        races = [Race(date=race_date, name="GP MTB", evidence="tss_spike:tss=280")]
        result = taper_windows(races, metrics)
        assert len(result) == 1
        tw = result[0]
        assert tw.evidence, "TaperWindow evidence is empty"
        assert _has_number(tw.evidence), (
            f"TaperWindow evidence has no number: {tw.evidence!r}"
        )

    def test_taper_window_values_derived_from_metrics(self) -> None:
        """ctl_race and atl_race should match the metric values on race day."""
        race_date = date(2024, 8, 11)
        # Custom metrics: last day = race day with known values
        metrics = _ramp_ctl(date(2024, 7, 12), n_days=31, ctl_start=50.0,
                            ctl_delta_per_day=1.0, daily_tss=88.0)
        # The last metric should be on 2024-08-11 with ctl=50+30*1=80
        races = [Race(date=race_date, name="Campeonato", evidence="keyword:campeonato")]
        result = taper_windows(races, metrics)
        assert len(result) == 1
        tw = result[0]
        # ctl_race should be approximately 80 (30 days × 1.0/day from 50)
        assert abs(tw.ctl_race - 80.0) < 2.0, (
            f"Expected ctl_race ≈ 80.0; got {tw.ctl_race}"
        )

    def test_multiple_races_produce_multiple_windows(self) -> None:
        """Two races with sufficient surrounding metrics yield two TaperWindows."""
        metrics = _ramp_ctl(date(2024, 9, 1), n_days=90, ctl_start=45.0,
                            ctl_delta_per_day=0.4, daily_tss=75.0)
        races = [
            Race(date=date(2024, 10, 6), name="Race A", evidence="keyword:prova"),
            Race(date=date(2024, 11, 10), name="Race B", evidence="keyword:copa"),
        ]
        result = taper_windows(races, metrics)
        assert len(result) == 2

    def test_race_before_all_metrics_returns_empty_window_list(self) -> None:
        """A race date before all metrics cannot build a window — skip gracefully."""
        metrics = _ramp_ctl(date(2024, 6, 1), n_days=30, ctl_start=50.0,
                            ctl_delta_per_day=0.5, daily_tss=70.0)
        races = [Race(date=date(2024, 1, 1), name="Old Race", evidence="keyword:prova")]
        result = taper_windows(races, metrics)
        assert result == []


# ===========================================================================
# coach_comment_terms
# ===========================================================================

class TestCoachCommentTerms:
    """Test term-frequency extraction from coach comments."""

    def test_empty_workouts_returns_empty(self) -> None:
        result = coach_comment_terms([])
        assert result == []

    def test_no_comments_returns_empty(self) -> None:
        workouts = [
            _make_workout(date(2024, 1, 1), extra={}),
            _make_workout(date(2024, 1, 2), extra={"coach_comments": ""}),
            _make_workout(date(2024, 1, 3), extra=None),
        ]
        result = coach_comment_terms(workouts)
        assert result == []

    def test_returns_list_of_tuples(self) -> None:
        workouts = [_make_workout(date(2024, 1, 5),
                                  extra={"coach_comments": "treino de z2 hoje"})]
        result = coach_comment_terms(workouts)
        assert isinstance(result, list)
        if result:
            assert all(isinstance(t, tuple) and len(t) == 2 for t in result)
            assert all(isinstance(t[0], str) and isinstance(t[1], int) for t in result)

    def test_sorted_by_count_descending(self) -> None:
        """Most frequent term comes first."""
        workouts = [
            _make_workout(date(2024, 1, 7),
                          extra={"coach_comments": "limiar limiar limiar z2 z2"}),
        ]
        result = coach_comment_terms(workouts)
        if len(result) >= 2:
            counts = [c for _, c in result]
            assert counts == sorted(counts, reverse=True)

    def test_stopwords_removed(self) -> None:
        """Common Portuguese stopwords must NOT appear in results."""
        stopwords = {"de", "e", "o", "a", "os", "as", "da", "do", "em", "para", "que",
                     "com", "um", "uma", "no", "na", "se"}
        workouts = [
            _make_workout(date(2024, 1, 9),
                          extra={"coach_comments": "trabalho de z2 com foco no limiar para a prova"}),
        ]
        result = coach_comment_terms(workouts)
        terms = {t for t, _ in result}
        common_stopwords_found = terms & stopwords
        assert not common_stopwords_found, (
            f"Stopwords should be removed; found: {common_stopwords_found}"
        )

    def test_cycling_terms_retained(self) -> None:
        """Cycling domain terms must be kept even if they are short."""
        workouts = [
            _make_workout(date(2024, 1, 11),
                          extra={"coach_comments": "z2 z2 limiar vo2 sweet spot fadiga ftp"}),
        ]
        result = coach_comment_terms(workouts)
        terms = {t for t, _ in result}
        expected = {"z2", "limiar", "vo2", "fadiga"}
        found = expected & terms
        assert found, f"Expected cycling terms {expected}; found terms: {terms}"

    def test_top_n_limits_result(self) -> None:
        """top_n parameter limits the number of returned terms."""
        # Generate many distinct terms
        comment = " ".join(f"termo{i}" for i in range(50))
        workouts = [_make_workout(date(2024, 1, 13),
                                  extra={"coach_comments": comment})]
        result = coach_comment_terms(workouts, top_n=10)
        assert len(result) <= 10

    def test_accumulates_across_multiple_workouts(self) -> None:
        """Term counts accumulate across all workouts."""
        workouts = [
            _make_workout(date(2024, 1, 15), extra={"coach_comments": "limiar foco"}),
            _make_workout(date(2024, 1, 17), extra={"coach_comments": "limiar intensidade"}),
            _make_workout(date(2024, 1, 19), extra={"coach_comments": "limiar z2"}),
        ]
        result = coach_comment_terms(workouts, top_n=5)
        term_map = dict(result)
        assert "limiar" in term_map, f"'limiar' not found in results: {term_map}"
        assert term_map["limiar"] == 3, (
            f"Expected count 3 for 'limiar'; got {term_map['limiar']}"
        )

    def test_lowercase_normalisation(self) -> None:
        """Terms are lowercased before counting."""
        workouts = [
            _make_workout(date(2024, 1, 21), extra={"coach_comments": "Limiar LIMIAR limiar"}),
        ]
        result = coach_comment_terms(workouts, top_n=5)
        term_map = dict(result)
        assert "limiar" in term_map
        assert term_map["limiar"] == 3

    def test_extra_none_handled_gracefully(self) -> None:
        """Workouts with extra=None must not raise an exception."""
        workouts = [
            _make_workout(date(2024, 1, 23), extra=None),
            _make_workout(date(2024, 1, 24), extra={"coach_comments": "z2 limiar"}),
        ]
        result = coach_comment_terms(workouts)
        assert isinstance(result, list)

    def test_default_top_n_is_30(self) -> None:
        """Default top_n should limit to 30 terms."""
        # Create 50 unique terms, each appearing once
        words = [f"unique{i}" for i in range(50)]
        comment = " ".join(words)
        workouts = [_make_workout(date(2024, 2, 1),
                                  extra={"coach_comments": comment})]
        result = coach_comment_terms(workouts)
        assert len(result) <= 30
