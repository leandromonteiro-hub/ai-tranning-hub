"""TDD tests for the TrainingPeaks metrics.csv parser (long format).

metrics.csv columns: Timestamp, Type, Value
Types: HRV, Pulse (resting HR = min of day), Sleep Hours, Notes, and others (unmapped).
"""
from __future__ import annotations

import io

import pandas as pd
import pytest

from app.services.ingestion.tp_metrics import TpDailyMetric, parse_tp_metrics


def _build_csv(rows: list[dict]) -> bytes:
    """Build an in-memory metrics.csv from a list of dicts."""
    df = pd.DataFrame(rows, columns=["Timestamp", "Type", "Value"])
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


SAMPLE_CSV = _build_csv(
    [
        # --- Day 1: 2026-01-10 ---
        {"Timestamp": "2026-01-10 07:00:00", "Type": "HRV", "Value": "65.2"},
        # Two Pulse readings same day → resting_hr = round(min) = 52
        {"Timestamp": "2026-01-10 07:05:00", "Type": "Pulse", "Value": "60"},
        {"Timestamp": "2026-01-10 07:10:00", "Type": "Pulse", "Value": "52"},
        {"Timestamp": "2026-01-10 08:00:00", "Type": "Sleep Hours", "Value": "7.5"},
        {"Timestamp": "2026-01-10 08:05:00", "Type": "Notes", "Value": "ok"},
        # Unmapped type
        {"Timestamp": "2026-01-10 08:10:00", "Type": "Time Awake", "Value": "0.25"},
        # --- Day 2: 2026-01-11 (only sleep, no HRV/Pulse/Notes) ---
        {"Timestamp": "2026-01-11 08:00:00", "Type": "Sleep Hours", "Value": "6.0"},
    ]
)


def test_parse_returns_two_days():
    metrics, report = parse_tp_metrics(SAMPLE_CSV)
    assert len(metrics) == 2


def test_day1_hrv():
    metrics, _ = parse_tp_metrics(SAMPLE_CSV)
    day1 = metrics[0]
    assert day1.hrv_ms == pytest.approx(65.2)


def test_day1_resting_hr_is_min_pulse():
    """resting_hr = round(min(Pulse readings)) for the day."""
    metrics, _ = parse_tp_metrics(SAMPLE_CSV)
    day1 = metrics[0]
    assert day1.resting_hr == 52  # min(60, 52) = 52


def test_day1_sleep_hours():
    metrics, _ = parse_tp_metrics(SAMPLE_CSV)
    day1 = metrics[0]
    assert day1.sleep_hours == pytest.approx(7.5)


def test_day1_comment():
    metrics, _ = parse_tp_metrics(SAMPLE_CSV)
    day1 = metrics[0]
    assert day1.comment == "ok"


def test_day2_sleep_only():
    metrics, _ = parse_tp_metrics(SAMPLE_CSV)
    day2 = metrics[1]
    assert day2.sleep_hours == pytest.approx(6.0)
    assert day2.hrv_ms is None
    assert day2.resting_hr is None
    assert day2.comment is None


def test_report_unmapped_types():
    _, report = parse_tp_metrics(SAMPLE_CSV)
    assert "Time Awake" in report["unmapped_types"]
    assert report["unmapped_types"]["Time Awake"] == 1


def test_report_row_count():
    _, report = parse_tp_metrics(SAMPLE_CSV)
    # 7 data rows in the sample
    assert report["rows"] == 7


def test_sorted_by_date():
    metrics, _ = parse_tp_metrics(SAMPLE_CSV)
    dates = [m.metric_date for m in metrics]
    assert dates == sorted(dates)


def test_metric_dates():
    from datetime import date

    metrics, _ = parse_tp_metrics(SAMPLE_CSV)
    assert metrics[0].metric_date.isoformat() == "2026-01-10"
    assert metrics[1].metric_date.isoformat() == "2026-01-11"


def test_non_numeric_value_skipped():
    """A non-numeric Value for HRV should not crash; that reading is skipped."""
    csv = _build_csv(
        [
            {"Timestamp": "2026-03-01 07:00:00", "Type": "HRV", "Value": "n/a"},
            {"Timestamp": "2026-03-01 07:00:00", "Type": "Sleep Hours", "Value": "7.0"},
        ]
    )
    metrics, _ = parse_tp_metrics(csv)
    assert len(metrics) == 1
    assert metrics[0].hrv_ms is None
    assert metrics[0].sleep_hours == pytest.approx(7.0)


def test_empty_csv_returns_empty():
    csv = _build_csv([])
    metrics, report = parse_tp_metrics(csv)
    assert metrics == []
    assert report["rows"] == 0
