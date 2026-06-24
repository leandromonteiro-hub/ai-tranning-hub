"""TDD tests for TrainingPeaks workouts.csv parser (wide format).

Synthetic CSV built via pandas.DataFrame.to_csv — no real athlete data.

Row types exercised:
  (a) completed Bike row — has executed signals (TimeTotalInHours, TSS, IF, etc.)
  (b) planned-only row — has PlannedDuration/WorkoutDescription, no executed signals
  (c) Day Off row — counted as rest_day, not persisted
"""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import pytest

from app.models.enums import WorkoutType
from app.services.ingestion.tp_workouts import TpPlanned, parse_tp_workouts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_csv(rows: list[dict]) -> bytes:
    """Build a workouts.csv from a list of row dicts."""
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------

COMPLETED_ROW = {
    "WorkoutDay": "2026-03-10",
    "WorkoutType": "Bike",
    "Title": "Morning Ride",
    "WorkoutDescription": "desc with\nnewline",
    "TimeTotalInHours": 1.5,
    "TSS": 70.0,
    "IF": 0.8,
    "PowerAverage": 200.0,
    "PowerMax": 600.0,
    "DistanceInMeters": 45000.0,
    "HeartRateAverage": 140.0,
    "HeartRateMax": 175.0,
    "CadenceAverage": 88.0,
    "VelocityAverage": None,
    "VelocityMax": None,
    "TorqueAverage": None,
    "TorqueMax": None,
    "Rpe": 7.0,
    "Feeling": 4.0,
    "CoachComments": "Z2 work",
    "AthleteComments": "senti bem",
    "PlannedDuration": None,
    "PlannedDistanceInMeters": None,
    # PWR zone minutes: zone 2 has 40 min, rest zero
    "PWRZone1Minutes": 10.0,
    "PWRZone2Minutes": 40.0,
    "PWRZone3Minutes": 0.0,
    "PWRZone4Minutes": 0.0,
    "PWRZone5Minutes": 0.0,
    "PWRZone6Minutes": 0.0,
    "PWRZone7Minutes": 0.0,
    "PWRZone8Minutes": 0.0,
    "PWRZone9Minutes": 0.0,
    "PWRZone10Minutes": 0.0,
    # HR zones all zero to keep it simple
    **{f"HRZone{i}Minutes": 0.0 for i in range(1, 11)},
}

PLANNED_ONLY_ROW = {
    "WorkoutDay": "2026-03-11",
    "WorkoutType": "Bike",
    "Title": "Base Ride",
    "WorkoutDescription": "base aerobic",
    "TimeTotalInHours": None,
    "TSS": None,
    "IF": None,
    "PowerAverage": None,
    "PowerMax": None,
    "DistanceInMeters": None,
    "HeartRateAverage": None,
    "HeartRateMax": None,
    "CadenceAverage": None,
    "VelocityAverage": None,
    "VelocityMax": None,
    "TorqueAverage": None,
    "TorqueMax": None,
    "Rpe": None,
    "Feeling": None,
    "CoachComments": None,
    "AthleteComments": None,
    "PlannedDuration": 2.0,
    "PlannedDistanceInMeters": None,
    **{f"PWRZone{i}Minutes": None for i in range(1, 11)},
    **{f"HRZone{i}Minutes": None for i in range(1, 11)},
}

DAY_OFF_ROW = {
    "WorkoutDay": "2026-03-12",
    "WorkoutType": "Day Off",
    "Title": None,
    "WorkoutDescription": None,
    "TimeTotalInHours": None,
    "TSS": None,
    "IF": None,
    "PowerAverage": None,
    "PowerMax": None,
    "DistanceInMeters": None,
    "HeartRateAverage": None,
    "HeartRateMax": None,
    "CadenceAverage": None,
    "VelocityAverage": None,
    "VelocityMax": None,
    "TorqueAverage": None,
    "TorqueMax": None,
    "Rpe": None,
    "Feeling": None,
    "CoachComments": None,
    "AthleteComments": None,
    "PlannedDuration": None,
    "PlannedDistanceInMeters": None,
    **{f"PWRZone{i}Minutes": None for i in range(1, 11)},
    **{f"HRZone{i}Minutes": None for i in range(1, 11)},
}

SAMPLE_CSV = _build_csv([COMPLETED_ROW, PLANNED_ONLY_ROW, DAY_OFF_ROW])


# ---------------------------------------------------------------------------
# Tests — report / counts
# ---------------------------------------------------------------------------

def test_report_counts():
    _, _, report = parse_tp_workouts(SAMPLE_CSV)
    assert report["rows"] == 3
    assert report["completed"] == 1
    assert report["planned"] == 1
    assert report["rest_days"] == 1


# ---------------------------------------------------------------------------
# Tests — completed activity
# ---------------------------------------------------------------------------

def test_completed_count():
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    assert len(completed) == 1


def test_completed_sport():
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    assert completed[0].sport == "cycling"


def test_completed_workout_type_from_if():
    """IF=0.8 falls in TEMPO band (0.75–0.85)."""
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    assert completed[0].workout_type == WorkoutType.TEMPO


def test_completed_duration_s():
    """1.5 h * 3600 = 5400 s."""
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    assert completed[0].duration_s == 5400


def test_completed_started_at():
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    assert completed[0].started_at == datetime(2026, 3, 10, 0, 0, 0)


def test_completed_avg_power():
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    assert completed[0].avg_power == pytest.approx(200.0)


def test_completed_source_tss_and_if():
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    act = completed[0]
    assert act.source_tss == pytest.approx(70.0)
    assert act.source_if == pytest.approx(0.8)


def test_completed_notes_is_workout_description():
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    assert completed[0].notes == "desc with\nnewline"


def test_completed_extra_power_max():
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    assert completed[0].extra["power_max"] == pytest.approx(600.0)


def test_completed_extra_rpe_and_feeling():
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    extra = completed[0].extra
    assert extra["rpe"] == pytest.approx(7.0)
    assert extra["feeling"] == pytest.approx(4.0)


def test_completed_extra_comments():
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    extra = completed[0].extra
    assert extra["coach_comments"] == "Z2 work"
    assert extra["athlete_comments"] == "senti bem"


def test_completed_extra_pwr_zone_minutes_length():
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    pwr = completed[0].extra["pwr_zone_minutes"]
    assert len(pwr) == 10


def test_completed_extra_pwr_zone_2_value():
    """Zone 2 was 40 min in the synthetic data."""
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    pwr = completed[0].extra["pwr_zone_minutes"]
    assert pwr[1] == pytest.approx(40.0)  # 0-indexed: zone2 = index 1


# ---------------------------------------------------------------------------
# Tests — planned workouts
# ---------------------------------------------------------------------------

def test_planned_count():
    _, planned, _ = parse_tp_workouts(SAMPLE_CSV)
    assert len(planned) == 1


def test_planned_duration_s():
    """PlannedDuration=2.0 h → 7200 s."""
    _, planned, _ = parse_tp_workouts(SAMPLE_CSV)
    assert planned[0].planned_duration_s == 7200


def test_planned_description():
    _, planned, _ = parse_tp_workouts(SAMPLE_CSV)
    assert planned[0].description == "base aerobic"


def test_planned_date():
    from datetime import date
    _, planned, _ = parse_tp_workouts(SAMPLE_CSV)
    assert planned[0].planned_date == date(2026, 3, 11)


# ---------------------------------------------------------------------------
# Tests — edge cases
# ---------------------------------------------------------------------------

def test_empty_csv_returns_empty():
    empty_csv = _build_csv([])
    completed, planned, report = parse_tp_workouts(empty_csv)
    assert completed == []
    assert planned == []
    assert report["rows"] == 0


def test_mtb_maps_to_cycling():
    row = {**COMPLETED_ROW, "WorkoutDay": "2026-04-01", "WorkoutType": "MTB"}
    csv = _build_csv([row])
    completed, _, _ = parse_tp_workouts(csv)
    assert completed[0].sport == "cycling"


def test_swim_maps_to_swim():
    row = {**COMPLETED_ROW, "WorkoutDay": "2026-04-02", "WorkoutType": "Swim"}
    csv = _build_csv([row])
    completed, _, _ = parse_tp_workouts(csv)
    assert completed[0].sport == "swim"


def test_strength_maps_to_strength():
    row = {**COMPLETED_ROW, "WorkoutDay": "2026-04-03", "WorkoutType": "Strength"}
    csv = _build_csv([row])
    completed, _, _ = parse_tp_workouts(csv)
    assert completed[0].sport == "strength"


def test_extra_default_is_empty_dict():
    """NormalizedActivity.extra defaults to {} (no KeyError on missing fields)."""
    from app.services.ingestion.normalizer import NormalizedActivity
    from datetime import datetime
    act = NormalizedActivity(started_at=datetime(2026, 1, 1))
    assert act.extra == {}


def test_multiline_description_survives_csv_roundtrip():
    """WorkoutDescription with embedded newline must not break parsing."""
    completed, _, _ = parse_tp_workouts(SAMPLE_CSV)
    # The description "desc with\nnewline" should survive the CSV roundtrip intact.
    assert completed[0].notes == "desc with\nnewline"


def test_row_yields_both_completed_and_planned():
    """A single row with BOTH planned and executed signals yields one of each."""
    row = {
        **COMPLETED_ROW,
        "WorkoutDay": "2026-05-01",
        "WorkoutType": "Bike",
        "TimeTotalInHours": 1.5,
        "TSS": 70.0,
        "PlannedDuration": 2.0,
    }
    csv = _build_csv([row])
    completed, planned, report = parse_tp_workouts(csv)

    assert len(completed) == 1
    assert len(planned) == 1
    assert completed[0].duration_s == 5400  # 1.5 h executed
    assert planned[0].planned_duration_s == 7200  # 2.0 h planned
    assert report["completed"] == 1
    assert report["planned"] == 1
