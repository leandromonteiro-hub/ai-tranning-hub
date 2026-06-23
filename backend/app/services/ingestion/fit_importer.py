"""FIT file importer using fitparse.

Extracts the session summary and the per-second record stream (power, HR,
cadence, altitude). NP/TSS are recomputed downstream from the power stream
against the FTP valid on the activity date.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from fitparse import FitFile

from app.core.logging import get_logger
from app.services.ingestion.normalizer import NormalizedActivity

log = get_logger(__name__)


def parse_fit(data: bytes) -> list[NormalizedActivity]:
    """Parse a FIT file into a single normalized activity (with streams)."""
    fit = FitFile(io.BytesIO(data))

    power: list[float] = []
    hr: list[float] = []
    cadence: list[float] = []
    altitude: list[float] = []
    started_at: datetime | None = None

    for record in fit.get_messages("record"):
        values = {d.name: d.value for d in record}
        if started_at is None and values.get("timestamp"):
            ts = values["timestamp"]
            started_at = ts if isinstance(ts, datetime) else None
        if values.get("power") is not None:
            power.append(float(values["power"]))
        if values.get("heart_rate") is not None:
            hr.append(float(values["heart_rate"]))
        if values.get("cadence") is not None:
            cadence.append(float(values["cadence"]))
        if values.get("altitude") is not None:
            altitude.append(float(values["altitude"]))

    # Session summary (preferred for totals).
    session = None
    for msg in fit.get_messages("session"):
        session = {d.name: d.value for d in msg}
        break

    if started_at is None and session and session.get("start_time"):
        started_at = session["start_time"]
    if started_at is None:
        # No usable timestamp — cannot place this activity in history.
        log.warning("fit_no_timestamp")
        return []
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    duration_s = None
    distance_m = None
    elevation = None
    avg_power = None
    avg_hr = None
    max_hr = None
    avg_cadence = None
    if session:
        duration_s = _to_int(session.get("total_timer_time"))
        distance_m = _to_float(session.get("total_distance"))
        elevation = _to_float(session.get("total_ascent"))
        avg_power = _to_float(session.get("avg_power"))
        avg_hr = _to_float(session.get("avg_heart_rate"))
        max_hr = _to_float(session.get("max_heart_rate"))
        avg_cadence = _to_float(session.get("avg_cadence"))

    if avg_power is None and power:
        avg_power = sum(power) / len(power)
    if duration_s is None and power:
        duration_s = len(power)

    act = NormalizedActivity(
        started_at=started_at,
        name=None,
        duration_s=duration_s,
        distance_m=distance_m,
        elevation_gain_m=elevation,
        avg_power=avg_power,
        avg_hr=avg_hr,
        max_hr=max_hr,
        avg_cadence=avg_cadence,
        power_stream=power,
        hr_stream=hr,
        cadence_stream=cadence,
        altitude_stream=altitude,
    )
    log.info(
        "fit_parsed",
        extra={"power_samples": len(power), "duration_s": duration_s},
    )
    return [act]


def _to_int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _to_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
