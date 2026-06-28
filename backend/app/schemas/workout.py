"""Workout schemas."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import WorkoutType


class WorkoutCompletedBase(BaseModel):
    started_at: datetime
    name: str | None = None
    workout_type: WorkoutType = WorkoutType.OTHER
    sport: str = "cycling"
    duration_s: int | None = None
    distance_m: float | None = None
    elevation_gain_m: float | None = None
    avg_power: float | None = None
    normalized_power: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    avg_cadence: float | None = None
    notes: str | None = None


class WorkoutCompletedCreate(WorkoutCompletedBase):
    external_id: str | None = None


class WorkoutCompletedRead(WorkoutCompletedBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    athlete_id: uuid.UUID
    workout_date: date
    tss: float | None = None
    intensity_factor: float | None = None
    ftp_used: float | None = None
    kj: float | None = None


class ImportedFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    filename: str
    file_format: str
    status: str
    rows_imported: int
    error_message: str | None = None
    created_at: datetime


class UploadResponse(BaseModel):
    """Response for POST /imports/upload: imported files + the async profile
    regeneration task id (None when no regen was enqueued)."""

    files: list[ImportedFileRead]
    profile_task_id: str | None = None
