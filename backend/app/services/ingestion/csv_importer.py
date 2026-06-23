"""CSV importer, primarily for TrainingPeaks workout exports.

TrainingPeaks column names vary by export; we match a set of known aliases
case-insensitively and fall back gracefully when a field is absent. Pre-computed
TSS/IF/NP from the source are preserved as ``source_*`` (real measured values),
never silently merged with our own recomputations.
"""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd

from app.core.logging import get_logger
from app.services.ingestion.normalizer import (
    NormalizedActivity,
    classify_workout_type,
)

log = get_logger(__name__)

# Map normalized field -> list of accepted source column names (lowercased).
COLUMN_ALIASES: dict[str, list[str]] = {
    "date": ["workoutday", "date", "timestamp", "starttime", "day"],
    "title": ["title", "name", "workouttitle"],
    "sport": ["workouttype", "sport", "activitytype"],
    "duration_h": ["timetotalinhours", "durationhours"],
    "duration_s": ["timetotalinseconds", "durationseconds", "elapsedtime", "movingtime"],
    "distance_m": ["distanceinmeters", "distance"],
    "elevation": ["elevationgain", "totalascent", "ascent"],
    "tss": ["tss", "trainingstressscore"],
    "if": ["if", "intensityfactor"],
    "np": ["normalizedpower", "np"],
    "avg_power": ["averagepower", "avgpower", "power"],
    "avg_hr": ["averageheartrate", "avghr", "heartrate"],
    "max_hr": ["maxheartrate", "maxhr"],
    "avg_cadence": ["averagecadence", "avgcadence", "cadence"],
    "external_id": ["id", "workoutid", "activityid"],
}


def _build_index(columns: list[str]) -> dict[str, str]:
    """Resolve normalized field -> actual column name present in the file."""
    lower = {c.lower().strip(): c for c in columns}
    resolved: dict[str, str] = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower:
                resolved[field] = lower[alias]
                break
    return resolved


def _num(row: pd.Series, idx: dict[str, str], field: str) -> float | None:
    col = idx.get(field)
    if not col:
        return None
    val = row.get(col)
    if pd.isna(val):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_date(value) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return pd.to_datetime(value).to_pydatetime()
    except (ValueError, TypeError):
        return None


def parse_csv(data: bytes) -> list[NormalizedActivity]:
    """Parse a TrainingPeaks-style CSV into normalized activities."""
    df = pd.read_csv(io.BytesIO(data))
    if df.empty:
        return []
    idx = _build_index(list(df.columns))

    activities: list[NormalizedActivity] = []
    for _, row in df.iterrows():
        started = _parse_date(row.get(idx["date"])) if "date" in idx else None
        if started is None:
            continue

        duration_s = None
        if "duration_s" in idx:
            d = _num(row, idx, "duration_s")
            duration_s = int(d) if d else None
        if duration_s is None and "duration_h" in idx:
            h = _num(row, idx, "duration_h")
            duration_s = int(h * 3600) if h else None

        if_value = _num(row, idx, "if")
        title = None
        if "title" in idx and not pd.isna(row.get(idx["title"])):
            title = str(row.get(idx["title"]))
        external_id = None
        if "external_id" in idx and not pd.isna(row.get(idx["external_id"])):
            external_id = str(row.get(idx["external_id"]))

        act = NormalizedActivity(
            started_at=started,
            name=title,
            workout_type=classify_workout_type(if_value),
            duration_s=duration_s,
            distance_m=_num(row, idx, "distance_m"),
            elevation_gain_m=_num(row, idx, "elevation"),
            avg_power=_num(row, idx, "avg_power"),
            avg_hr=_num(row, idx, "avg_hr"),
            max_hr=_num(row, idx, "max_hr"),
            avg_cadence=_num(row, idx, "avg_cadence"),
            external_id=external_id,
            source_tss=_num(row, idx, "tss"),
            source_if=if_value,
            source_np=_num(row, idx, "np"),
        )
        activities.append(act)

    log.info("csv_parsed", extra={"rows": len(df), "activities": len(activities)})
    return activities
