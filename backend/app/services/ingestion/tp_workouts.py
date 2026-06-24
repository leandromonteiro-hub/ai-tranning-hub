"""TrainingPeaks workouts.csv parser (wide format).

One row per workout. Columns include executed signals (TimeTotalInHours, TSS, etc.)
and planned signals (PlannedDuration, PlannedDistanceInMeters, WorkoutDescription).
A row may yield a completed NormalizedActivity, a TpPlanned, or both.
``WorkoutType == "Day Off"`` rows are counted as rest days and not persisted.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from app.models.enums import WorkoutType
from app.services.ingestion.normalizer import NormalizedActivity, classify_workout_type

# ---------------------------------------------------------------------------
# Column aliases (wide workouts.csv) — normalised field -> lowercased aliases
# ---------------------------------------------------------------------------
_ALIASES: dict[str, list[str]] = {
    "workout_day": ["workoutday"],
    "workout_type_col": ["workouttype"],
    "title": ["title"],
    "workout_description": ["workoutdescription"],
    "planned_duration": ["plannedduration", "plannedduration (h)"],
    "planned_distance": ["planneddistanceinmeters"],
    "time_total_h": ["timetotalinhours"],
    "tss": ["tss"],
    "if_value": ["if"],
    "power_avg": ["poweraverage"],
    "power_max": ["powermax"],
    "distance_m": ["distanceinmeters"],
    "hr_avg": ["heartrateaverage"],
    "hr_max": ["heartratemax"],
    "cadence_avg": ["cadenceaverage"],
    "velocity_avg": ["velocityaverage"],
    "velocity_max": ["velocitymax"],
    "torque_avg": ["torqueaverage"],
    "torque_max": ["torquemax"],
    "rpe": ["rpe"],
    "feeling": ["feeling"],
    "coach_comments": ["coachcomments"],
    "athlete_comments": ["athletecomments"],
    # HR zone minutes: HRZone1Minutes … HRZone10Minutes
    **{f"hr_zone_{i}": [f"hrzone{i}minutes"] for i in range(1, 11)},
    # Power zone minutes: PWRZone1Minutes … PWRZone10Minutes
    **{f"pwr_zone_{i}": [f"pwrzone{i}minutes"] for i in range(1, 11)},
}

# Modality (WorkoutType CSV column) -> sport
_SPORT_MAP: dict[str, str] = {
    "bike": "cycling",
    "mtb": "cycling",
    "swim": "swim",
    "strength": "strength",
}


@dataclass
class TpPlanned:
    planned_date: date
    name: str
    sport: str
    workout_type: WorkoutType
    planned_duration_s: int | None
    planned_tss: float | None
    description: str | None
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_index(columns: list[str]) -> dict[str, str]:
    """Resolve normalised field name -> actual column present in the file."""
    lower = {c.lower().strip(): c for c in columns}
    resolved: dict[str, str] = {}
    for norm_field, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in lower:
                resolved[norm_field] = lower[alias]
                break
    return resolved


def _num(row: pd.Series, idx: dict[str, str], norm_field: str) -> float | None:
    col = idx.get(norm_field)
    if not col:
        return None
    val = row.get(col)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _str(row: pd.Series, idx: dict[str, str], norm_field: str) -> str | None:
    col = idx.get(norm_field)
    if not col:
        return None
    val = row.get(col)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s if s else None


def _parse_date(value) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return pd.to_datetime(value).date()
    except (ValueError, TypeError):
        return None


def _sport(row: pd.Series, idx: dict[str, str]) -> str:
    raw = _str(row, idx, "workout_type_col")
    if raw is None:
        return "cycling"
    return _SPORT_MAP.get(raw.lower().strip(), "other")


def _build_extra(row: pd.Series, idx: dict[str, str]) -> dict:
    """Build the extra dict, dropping None/empty values."""
    extra: dict = {}

    for key, norm_field in [
        ("power_max", "power_max"),
        ("velocity_avg", "velocity_avg"),
        ("velocity_max", "velocity_max"),
        ("torque_avg", "torque_avg"),
        ("torque_max", "torque_max"),
        ("rpe", "rpe"),
        ("feeling", "feeling"),
    ]:
        v = _num(row, idx, norm_field)
        if v is not None:
            extra[key] = v

    for key, norm_field in [
        ("coach_comments", "coach_comments"),
        ("athlete_comments", "athlete_comments"),
    ]:
        s = _str(row, idx, norm_field)
        if s is not None:
            extra[key] = s

    # HR zone minutes (list 1..10)
    hr_zones = [_num(row, idx, f"hr_zone_{i}") for i in range(1, 11)]
    if any(v is not None for v in hr_zones):
        extra["hr_zone_minutes"] = [v if v is not None else 0.0 for v in hr_zones]

    # Power zone minutes (list 1..10)
    pwr_zones = [_num(row, idx, f"pwr_zone_{i}") for i in range(1, 11)]
    if any(v is not None for v in pwr_zones):
        extra["pwr_zone_minutes"] = [v if v is not None else 0.0 for v in pwr_zones]

    return extra


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_tp_workouts(
    data: bytes,
) -> tuple[list[NormalizedActivity], list[TpPlanned], dict]:
    """Parse a TrainingPeaks workouts.csv export (wide format).

    Returns:
        (completed_activities, planned_workouts, report_dict)
    """
    try:
        df = pd.read_csv(io.BytesIO(data))
    except pd.errors.EmptyDataError:
        # Header-only or completely empty file — no rows to parse.
        # Any other parse error propagates so callers fail loudly.
        return [], [], {"rows": 0, "completed": 0, "planned": 0, "rest_days": 0}
    if df.empty:
        return [], [], {"rows": 0, "completed": 0, "planned": 0, "rest_days": 0}

    idx = _build_index(list(df.columns))

    completed: list[NormalizedActivity] = []
    planned: list[TpPlanned] = []
    rest_days = 0

    for _, row in df.iterrows():
        # --- Classify row ---
        workout_type_raw = _str(row, idx, "workout_type_col")
        is_rest = workout_type_raw is not None and workout_type_raw.lower() == "day off"

        if is_rest:
            rest_days += 1
            continue

        workout_day = _parse_date(row.get(idx["workout_day"])) if "workout_day" in idx else None
        if workout_day is None:
            continue

        # Executed signals
        time_total_h = _num(row, idx, "time_total_h")
        tss_val = _num(row, idx, "tss")
        power_avg = _num(row, idx, "power_avg")
        distance_m = _num(row, idx, "distance_m")
        has_executed = any(v is not None for v in [time_total_h, tss_val, power_avg, distance_m])

        # Planned signals: explicit planned columns, or description when not executed
        planned_duration_h = _num(row, idx, "planned_duration")
        planned_distance = _num(row, idx, "planned_distance")
        description = _str(row, idx, "workout_description")
        has_planned = (
            planned_duration_h is not None
            or planned_distance is not None
            or (description is not None and not has_executed)
        )

        title = _str(row, idx, "title") or ""
        sport = _sport(row, idx)

        # --- Build completed NormalizedActivity ---
        if has_executed:
            if_value = _num(row, idx, "if_value")
            duration_s = round(time_total_h * 3600) if time_total_h is not None else None
            extra = _build_extra(row, idx)

            act = NormalizedActivity(
                started_at=datetime(workout_day.year, workout_day.month, workout_day.day, 0, 0, 0),
                name=title or None,
                sport=sport,
                workout_type=classify_workout_type(if_value),
                duration_s=duration_s,
                distance_m=distance_m,
                avg_power=power_avg,
                avg_hr=_num(row, idx, "hr_avg"),
                max_hr=_num(row, idx, "hr_max"),
                avg_cadence=_num(row, idx, "cadence_avg"),
                source_tss=tss_val,
                source_if=if_value,
                notes=description,
                extra=extra,
            )
            completed.append(act)

        # --- Build TpPlanned ---
        if has_planned:
            planned_duration_s = (
                round(planned_duration_h * 3600) if planned_duration_h is not None else None
            )
            tp = TpPlanned(
                planned_date=workout_day,
                name=title or "",
                sport=sport,
                workout_type=WorkoutType.OTHER,
                planned_duration_s=planned_duration_s,
                planned_tss=None,
                description=description,
            )
            planned.append(tp)

    report = {
        "rows": len(df),
        "completed": len(completed),
        "planned": len(planned),
        "rest_days": rest_days,
    }
    return completed, planned, report
