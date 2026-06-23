"""Unit tests for the power/load metric calculators."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.metrics import tss_calculator
from app.services.metrics.load_calculator import compute_load_series, ramp_rate


def test_intensity_factor():
    assert tss_calculator.intensity_factor(250, 250) == pytest.approx(1.0)
    assert tss_calculator.intensity_factor(200, 250) == pytest.approx(0.8)
    assert tss_calculator.intensity_factor(None, 250) is None
    assert tss_calculator.intensity_factor(200, 0) is None


def test_tss_one_hour_at_ftp_is_100():
    # One hour exactly at FTP (NP == FTP, IF == 1.0) is 100 TSS by definition.
    tss = tss_calculator.tss_from_np(duration_s=3600, np_value=250, ftp=250)
    assert tss == pytest.approx(100.0, abs=0.01)


def test_tss_from_if():
    # 2h at IF 0.7 -> 2 * 0.49 * 100 = 98
    assert tss_calculator.tss_from_if(7200, 0.7) == pytest.approx(98.0)


def test_normalized_power_constant_stream_equals_power():
    stream = [200.0] * 600  # 10 min steady
    np_val = tss_calculator.normalized_power(stream)
    assert np_val == pytest.approx(200.0, abs=1.0)


def test_normalized_power_greater_than_average_for_variable():
    # Variable power: NP should exceed simple average.
    stream = ([100.0] * 30 + [300.0] * 30) * 20
    avg = sum(stream) / len(stream)
    np_val = tss_calculator.normalized_power(stream)
    assert np_val > avg


def test_kilojoules():
    stream = [200.0] * 3600  # 200 W for 1 h
    kj = tss_calculator.kilojoules(stream)
    assert kj == pytest.approx(720.0)  # 200 * 3600 / 1000


def test_load_series_builds_and_tsb_is_fitness_minus_fatigue():
    start = date(2026, 1, 1)
    tss_by_date = {start + timedelta(days=i): 100.0 for i in range(60)}
    series = compute_load_series(tss_by_date)
    assert len(series) == 60
    # After steady load, CTL and ATL rise; ATL rises faster so TSB goes negative.
    last = series[-1]
    assert last.ctl > 0
    assert last.atl > last.ctl  # acute > chronic under steady recent load
    assert last.tsb < 0


def test_load_series_rest_day_filled_with_zero():
    start = date(2026, 1, 1)
    tss_by_date = {start: 100.0, start + timedelta(days=5): 100.0}
    series = compute_load_series(tss_by_date)
    # Gap days are present and contribute 0 TSS.
    assert len(series) == 6
    assert series[1].daily_tss == 0.0


def test_tss_from_np_returns_none_on_missing_inputs():
    assert tss_calculator.tss_from_np(None, 200, 250) is None
    assert tss_calculator.tss_from_np(3600, None, 250) is None
    assert tss_calculator.tss_from_np(3600, 200, 0) is None


def test_normalized_power_empty_and_short_stream():
    assert tss_calculator.normalized_power([]) is None
    # Stream shorter than the 30s window falls back to the average.
    assert tss_calculator.normalized_power([150.0] * 10) == pytest.approx(150.0)


def test_kilojoules_none_on_empty():
    assert tss_calculator.kilojoules([]) is None


def test_estimate_tss_from_hr():
    # 1h at the midpoint of HR reserve -> non-trivial estimate.
    est = tss_calculator.estimate_tss_from_hr(
        duration_s=3600, avg_hr=150, resting_hr=50, max_hr=190
    )
    assert est is not None and est > 0
    # Missing inputs -> None (never silently assume).
    assert tss_calculator.estimate_tss_from_hr(3600, None, 50, 190) is None
    assert tss_calculator.estimate_tss_from_hr(3600, 150, 190, 190) is None  # reserve <= 0


def test_ramp_rate_positive_under_progressive_load():
    start = date(2026, 1, 1)
    tss_by_date = {start + timedelta(days=i): 80.0 for i in range(30)}
    series = compute_load_series(tss_by_date)
    assert ramp_rate(series, days=7) > 0
