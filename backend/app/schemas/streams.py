from __future__ import annotations

import uuid

from pydantic import BaseModel


class WorkoutStreamsRead(BaseModel):
    workout_id: uuid.UUID
    n_points: int
    time_s: list[float | None] = []
    power: list[float | None] = []
    heart_rate: list[float | None] = []
    cadence: list[float | None] = []
    altitude: list[float | None] = []
