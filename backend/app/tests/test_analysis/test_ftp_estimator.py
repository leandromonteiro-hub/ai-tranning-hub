"""Tests for ftp_estimator — TDD (red → green)."""
from __future__ import annotations

from datetime import date

import pytest

from app.services.analysis.ftp_estimator import (
    FtpEstimate,
    all_time_power_curve,
    estimate_ftp_timeline,
    is_plausible_power_stream,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _constant_stream(watts: float, seconds: int) -> list[float]:
    """Create a 1 Hz power stream of constant wattage."""
    return [watts] * seconds


# ---------------------------------------------------------------------------
# all_time_power_curve
# ---------------------------------------------------------------------------


class TestIsPlausiblePowerStream:
    def test_legit_stream_is_plausible(self) -> None:
        # 300 W for 25 min → best_20min = 300 ≤ 600 → plausible
        assert is_plausible_power_stream(_constant_stream(300.0, 25 * 60)) is True

    def test_corrupt_stream_is_implausible(self) -> None:
        # 1100 W for 25 min → best_20min = 1100 > 600 → implausible
        assert is_plausible_power_stream(_constant_stream(1100.0, 25 * 60)) is False

    def test_too_short_stream_treated_as_plausible(self) -> None:
        # 5-min stream at 1500 W cannot produce a 20-min value → plausible (judged elsewhere)
        assert is_plausible_power_stream(_constant_stream(1500.0, 5 * 60)) is True

    def test_at_ceiling_is_plausible(self) -> None:
        # Exactly at ceiling (600 W) → plausible (<=)
        assert is_plausible_power_stream(_constant_stream(600.0, 25 * 60)) is True

    def test_custom_ceiling(self) -> None:
        # 400 W stream with a 350 W ceiling → implausible
        assert is_plausible_power_stream(_constant_stream(400.0, 25 * 60), ceiling_20min_w=350.0) is False


class TestAllTimePowerCurve:
    def test_single_stream_returns_best_at_standard_durations(self) -> None:
        # 25-minute constant 300 W stream → best_20min should be 300 W
        stream = _constant_stream(300.0, 25 * 60)
        curve, excluded = all_time_power_curve([stream])
        assert curve[1200] == pytest.approx(300.0)
        assert excluded == 0

    def test_multiple_streams_picks_highest(self) -> None:
        # stream A: 250 W for 25 min; stream B: 310 W for 25 min
        # best_20min should be 310 (from stream B)
        stream_a = _constant_stream(250.0, 25 * 60)
        stream_b = _constant_stream(310.0, 25 * 60)
        curve, excluded = all_time_power_curve([stream_a, stream_b])
        assert curve[1200] == pytest.approx(310.0)
        assert excluded == 0

    def test_short_streams_excluded_from_longer_durations(self) -> None:
        # only a 5-min stream → 20-min key should not appear
        stream = _constant_stream(400.0, 5 * 60)
        curve, excluded = all_time_power_curve([stream])
        assert 1200 not in curve
        assert curve[300] == pytest.approx(400.0)
        assert excluded == 0

    def test_empty_list_returns_empty_dict(self) -> None:
        assert all_time_power_curve([]) == ({}, 0)

    def test_mixed_length_streams(self) -> None:
        # short stream at 500 W (only covers 5 min), long stream at 280 W (25 min)
        short = _constant_stream(500.0, 5 * 60)
        long = _constant_stream(280.0, 25 * 60)
        curve, excluded = all_time_power_curve([short, long])
        # 5-min best should be 500 (from short stream)
        assert curve[300] == pytest.approx(500.0)
        # 20-min best should be 280 (only long stream has it)
        assert curve[1200] == pytest.approx(280.0)
        assert excluded == 0

    def test_corrupt_stream_filtered_legit_curve_returned(self) -> None:
        # one corrupt (1100 W / 25 min) + one legit (300 W / 25 min)
        # → curve reflects ONLY the legit stream; excluded count == 1
        corrupt = _constant_stream(1100.0, 25 * 60)
        legit = _constant_stream(300.0, 25 * 60)
        curve, excluded = all_time_power_curve([corrupt, legit])
        assert curve[1200] == pytest.approx(300.0)
        assert excluded == 1


# ---------------------------------------------------------------------------
# estimate_ftp_timeline
# ---------------------------------------------------------------------------


class TestEstimateFtpTimeline:
    def test_single_window_with_20min_effort_uses_pc20(self) -> None:
        # 300 W for 25 min → best_20min = 300 → ftp = 0.95 × 300 = 285
        stream = _constant_stream(300.0, 25 * 60)
        windows = [
            (date(2024, 1, 1), date(2024, 3, 31), [stream]),
        ]
        result = estimate_ftp_timeline(windows)
        assert len(result) == 1
        est = result[0]
        assert isinstance(est, FtpEstimate)
        assert est.valid_from == date(2024, 1, 1)
        assert est.valid_to == date(2024, 3, 31)
        assert est.ftp_watts == pytest.approx(285.0)
        assert est.method == "estimate_pc20"

    def test_65min_stream_uses_pc20_not_pc60(self) -> None:
        # A continuous 65-min stream always yields a 20-min best too, so the pc20
        # path must win over pc60 — this confirms the priority order. The pc60
        # branch itself is exercised directly in the monkeypatch test below.
        stream_65min = _constant_stream(240.0, 65 * 60)
        windows = [
            (date(2024, 4, 1), date(2024, 6, 30), [stream_65min]),
        ]
        result = estimate_ftp_timeline(windows)
        assert len(result) == 1
        # A 65-min stream always yields a 20-min window → should use pc20
        assert result[0].method == "estimate_pc20"
        assert result[0].ftp_watts == pytest.approx(0.95 * 240.0)

    def test_estimate_pc60_branch_via_monkeypatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Force the pc60 branch by patching all_time_power_curve to return only 3600."""
        import app.services.analysis.ftp_estimator as mod

        monkeypatch.setattr(
            mod,
            "all_time_power_curve",
            lambda streams, **kw: ({3600: 250.0}, 0),
        )
        windows = [(date(2024, 4, 1), date(2024, 6, 30), [[]])]
        result = mod.estimate_ftp_timeline(windows)
        assert len(result) == 1
        assert result[0].method == "estimate_pc60"
        assert result[0].ftp_watts == pytest.approx(0.95 * 250.0)

    def test_window_with_no_usable_power_skipped(self) -> None:
        # Empty streams list → window should be skipped
        windows = [
            (date(2024, 7, 1), date(2024, 9, 30), []),
        ]
        result = estimate_ftp_timeline(windows)
        assert result == []

    def test_window_with_only_very_short_streams_skipped(self) -> None:
        # Streams all shorter than 60 min → no 20-min or 60-min value → skip
        short = _constant_stream(400.0, 5 * 60)  # 300 s < 1200 s
        windows = [
            (date(2024, 10, 1), None, [short]),
        ]
        result = estimate_ftp_timeline(windows)
        assert result == []

    def test_multiple_windows_all_computed(self) -> None:
        stream_q1 = _constant_stream(290.0, 25 * 60)
        stream_q2 = _constant_stream(305.0, 25 * 60)
        windows = [
            (date(2025, 1, 1), date(2025, 3, 31), [stream_q1]),
            (date(2025, 4, 1), date(2025, 6, 30), [stream_q2]),
        ]
        result = estimate_ftp_timeline(windows)
        assert len(result) == 2
        assert result[0].ftp_watts == pytest.approx(0.95 * 290.0)
        assert result[1].ftp_watts == pytest.approx(0.95 * 305.0)
        assert result[0].method == "estimate_pc20"
        assert result[1].method == "estimate_pc20"

    def test_valid_to_none_preserved(self) -> None:
        stream = _constant_stream(300.0, 25 * 60)
        windows = [
            (date(2025, 10, 1), None, [stream]),
        ]
        result = estimate_ftp_timeline(windows)
        assert len(result) == 1
        assert result[0].valid_to is None

    def test_empty_windows_list(self) -> None:
        assert estimate_ftp_timeline([]) == []

    def test_corrupt_stream_does_not_inflate_window_ftp(self) -> None:
        # corrupt (1100 W / 25 min) + legit (300 W / 25 min) in one window
        # → FTP must reflect the legit 20-min (≈ 285 W), not 0.95×1100
        corrupt = _constant_stream(1100.0, 25 * 60)
        legit = _constant_stream(300.0, 25 * 60)
        windows = [
            (date(2024, 1, 1), date(2024, 3, 31), [corrupt, legit]),
        ]
        result = estimate_ftp_timeline(windows)
        assert len(result) == 1
        assert result[0].ftp_watts == pytest.approx(285.0)
        assert result[0].method == "estimate_pc20"

    def test_window_with_only_corrupt_streams_skipped(self) -> None:
        # the only stream is corrupt → filtered out → no usable power → skip
        corrupt = _constant_stream(1100.0, 25 * 60)
        windows = [
            (date(2024, 1, 1), date(2024, 3, 31), [corrupt]),
        ]
        result = estimate_ftp_timeline(windows)
        assert result == []
