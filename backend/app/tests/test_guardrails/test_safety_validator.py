"""Tests for the safety guardrails that gate every recommendation."""
from __future__ import annotations

from app.models.enums import RiskLevel
from app.services.ai.safety_validator import (
    AthleteSafetySnapshot,
    evaluate_safety,
)


def test_all_clear_is_low_risk():
    snap = AthleteSafetySnapshot(
        ctl=60, atl=55, tsb=-5, ramp_rate_7d=3.0, monotony=1.2,
        weekly_tss_current=420, weekly_tss_previous=400,
        last_48h_sleep_h=7.5, hrv_recent=80, hrv_baseline=82,
        subjective_fatigue=2,
    )
    result = evaluate_safety(snap)
    assert result.risk_level == RiskLevel.LOW
    assert result.block_original is False
    assert result.flags == []


def test_single_borderline_is_moderate_with_warning():
    snap = AthleteSafetySnapshot(
        ctl=60, atl=70, tsb=-22,  # tsb warning band
        ramp_rate_7d=3.0, last_48h_sleep_h=7.5,
    )
    result = evaluate_safety(snap)
    assert result.risk_level == RiskLevel.MODERATE
    assert result.block_original is False
    assert any(f["indicator"] == "tsb" for f in result.flags)


def test_critical_tsb_blocks_and_is_high_risk():
    snap = AthleteSafetySnapshot(tsb=-35)
    result = evaluate_safety(snap)
    assert result.risk_level == RiskLevel.HIGH
    assert result.block_original is True


def test_recent_injury_is_critical():
    snap = AthleteSafetySnapshot(tsb=-5, recent_injury=True)
    result = evaluate_safety(snap)
    assert result.risk_level == RiskLevel.HIGH
    assert result.block_original is True


def test_weekly_load_increase_over_10pct_flags():
    snap = AthleteSafetySnapshot(
        weekly_tss_current=500, weekly_tss_previous=400,  # +25%
    )
    result = evaluate_safety(snap)
    assert any(f["indicator"] == "weekly_load_increase" for f in result.flags)
    # >20% is treated as critical -> high risk + block.
    assert result.risk_level == RiskLevel.HIGH


def test_hrv_drop_and_low_sleep_combine_to_at_least_moderate():
    snap = AthleteSafetySnapshot(
        last_48h_sleep_h=5.0, hrv_recent=60, hrv_baseline=80,  # 25% drop -> critical
    )
    result = evaluate_safety(snap)
    assert result.risk_level == RiskLevel.HIGH


def test_missing_values_are_skipped_not_assumed_safe_or_unsafe():
    # An empty snapshot has nothing to flag -> low (no data to act on).
    result = evaluate_safety(AthleteSafetySnapshot())
    assert result.risk_level == RiskLevel.LOW
    assert result.flags == []
