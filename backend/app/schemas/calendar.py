from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel

from app.schemas.planning import PlannedWorkoutRead
from app.schemas.workout import WorkoutCompletedRead


class RaceMarker(BaseModel):
    id: uuid.UUID
    name: str
    race_date: date
    days_until: int


class CalendarDay(BaseModel):
    date: date
    planned: list[PlannedWorkoutRead] = []
    completed: list[WorkoutCompletedRead] = []
    races: list[RaceMarker] = []


class WeekSummary(BaseModel):
    week_start: date
    ctl: float | None = None
    atl: float | None = None
    tsb: float | None = None
    total_duration_s: int = 0
    total_tss: float = 0.0
    total_distance_m: float = 0.0
    total_elevation_m: float = 0.0
    total_kj: float = 0.0


class CalendarResponse(BaseModel):
    days: list[CalendarDay] = []
    weeks: list[WeekSummary] = []
