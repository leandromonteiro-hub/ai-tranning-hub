"""Normalized representation of an imported activity.

Every importer (CSV/FIT/TCX/GPX) converts its source format into a
``NormalizedActivity``. Downstream metric computation and persistence only ever
see this neutral shape, keeping importers decoupled from storage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.models.enums import WorkoutType


@dataclass
class NormalizedActivity:
    started_at: datetime
    name: str | None = None
    sport: str = "cycling"
    workout_type: WorkoutType = WorkoutType.OTHER
    duration_s: int | None = None
    distance_m: float | None = None
    elevation_gain_m: float | None = None
    avg_power: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    avg_cadence: float | None = None
    external_id: str | None = None
    # Optional pre-computed values from the source (e.g. TrainingPeaks TSS)
    source_tss: float | None = None
    source_if: float | None = None
    source_np: float | None = None
    # Raw per-second streams (empty if not available)
    power_stream: list[float] = field(default_factory=list)
    hr_stream: list[float] = field(default_factory=list)
    cadence_stream: list[float] = field(default_factory=list)
    altitude_stream: list[float] = field(default_factory=list)
    notes: str | None = None


def classify_workout_type(if_value: float | None) -> WorkoutType:
    """Heuristic workout-type classification from intensity factor."""
    if if_value is None:
        return WorkoutType.OTHER
    if if_value < 0.60:
        return WorkoutType.RECOVERY
    if if_value < 0.75:
        return WorkoutType.ENDURANCE
    if if_value < 0.85:
        return WorkoutType.TEMPO
    if if_value < 0.95:
        return WorkoutType.SWEET_SPOT
    if if_value < 1.05:
        return WorkoutType.THRESHOLD
    if if_value < 1.15:
        return WorkoutType.VO2MAX
    return WorkoutType.ANAEROBIC
