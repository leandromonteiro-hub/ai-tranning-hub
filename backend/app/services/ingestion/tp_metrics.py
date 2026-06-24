"""Parser for TrainingPeaks metrics.csv export (long format).

The export has columns:  Timestamp, Type, Value
One row per reading; multiple readings per day are common (e.g. two Pulse values).

Produces:
    TpDailyMetric  — one per calendar date found in the file.
    parse_tp_metrics(data: bytes) -> tuple[list[TpDailyMetric], dict]
        The report dict: {"unmapped_types": {type_name: count}, "rows": n}

Type mapping (case-insensitive):
    HRV          -> hrv_ms      (float, first non-null reading of the day)
    Pulse        -> resting_hr  (int, round(min) of all readings — RHR is the
                                 lowest recorded heart rate of the day)
    Sleep Hours  -> sleep_hours (float, first non-null reading)
    Notes        -> comment     (str,  first non-empty string)
    <anything else>             -> counted in unmapped_types, not stored
"""
from __future__ import annotations

import io
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.core.logging import get_logger

log = get_logger(__name__)

# Case-insensitive type → internal field name
_TYPE_MAP: dict[str, str] = {
    "hrv": "hrv",
    "pulse": "pulse",
    "sleep hours": "sleep_hours",
    "notes": "notes",
}


@dataclass
class TpDailyMetric:
    metric_date: date
    hrv_ms: float | None = None
    resting_hr: int | None = None
    sleep_hours: float | None = None
    comment: str | None = None


def _to_float(value) -> float | None:
    """Return float or None; silently drops non-numeric values."""
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_tp_metrics(data: bytes) -> tuple[list[TpDailyMetric], dict]:
    """Parse a TrainingPeaks metrics.csv (long format) into daily metrics.

    Args:
        data: Raw bytes of the CSV file.

    Returns:
        (metrics, report) where metrics is a list of TpDailyMetric sorted by
        metric_date, and report is {"unmapped_types": {name: count}, "rows": n}.
    """
    df = pd.read_csv(io.BytesIO(data))

    if df.empty:
        log.info("tp_metrics_parsed", extra={"rows": 0, "days": 0})
        return [], {"unmapped_types": {}, "rows": 0}

    total_rows = len(df)

    # Normalise column names (strip whitespace)
    df.columns = [c.strip() for c in df.columns]

    # Parse Timestamp to date
    df["_date"] = pd.to_datetime(df["Timestamp"], errors="coerce").dt.date

    # Drop rows where the timestamp couldn't be parsed
    df = df.dropna(subset=["_date"])

    # Per-day accumulators
    hrv_by_day: dict[date, float] = {}
    pulse_by_day: dict[date, list[float]] = defaultdict(list)
    sleep_by_day: dict[date, float] = {}
    comment_by_day: dict[date, str] = {}
    unmapped: Counter = Counter()

    for _, row in df.iterrows():
        day: date = row["_date"]
        type_raw: str = str(row["Type"]).strip()
        field_key = _TYPE_MAP.get(type_raw.lower())

        if field_key is None:
            unmapped[type_raw] += 1
            continue

        value_raw = row["Value"]

        if field_key == "hrv":
            v = _to_float(value_raw)
            if v is not None and day not in hrv_by_day:
                hrv_by_day[day] = v

        elif field_key == "pulse":
            v = _to_float(value_raw)
            if v is not None:
                pulse_by_day[day].append(v)

        elif field_key == "sleep_hours":
            v = _to_float(value_raw)
            if v is not None and day not in sleep_by_day:
                sleep_by_day[day] = v

        elif field_key == "notes":
            text = str(value_raw).strip() if not pd.isna(value_raw) else ""
            if text and day not in comment_by_day:
                comment_by_day[day] = text

    # Collect all days seen
    all_days: set[date] = (
        set(hrv_by_day)
        | set(pulse_by_day)
        | set(sleep_by_day)
        | set(comment_by_day)
    )

    metrics: list[TpDailyMetric] = []
    for day in sorted(all_days):
        rhr: int | None = None
        if pulse_by_day[day]:
            rhr = round(min(pulse_by_day[day]))

        metrics.append(
            TpDailyMetric(
                metric_date=day,
                hrv_ms=hrv_by_day.get(day),
                resting_hr=rhr,
                sleep_hours=sleep_by_day.get(day),
                comment=comment_by_day.get(day),
            )
        )

    report = {
        "unmapped_types": dict(unmapped),
        "rows": total_rows,
    }

    log.info(
        "tp_metrics_parsed",
        extra={"rows": total_rows, "days": len(metrics), "unmapped": dict(unmapped)},
    )
    return metrics, report
