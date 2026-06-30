"""Plain data types crossing the Garmin client boundary (no lib imports)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class ActivityRef:
    activity_id: str
    start_time: datetime
    name: str | None = None


@dataclass(frozen=True)
class WellnessSnapshot:
    day: date
    hrv_ms: float | None = None
    resting_hr: int | None = None
    sleep_hours: float | None = None
    sleep_score: float | None = None
    body_battery: float | None = None


@dataclass(frozen=True)
class Connected:
    token: dict


@dataclass(frozen=True)
class NeedsMfa:
    client_state: dict


LoginResult = Connected | NeedsMfa
