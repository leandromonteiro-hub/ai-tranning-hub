"""Race, result and analysis schemas."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class RaceCreate(BaseModel):
    name: str
    race_date: date
    discipline: str | None = None
    priority: str = Field(default="A", pattern="^[ABC]$")
    location: str | None = None
    distance_km: float | None = None
    elevation_gain_m: float | None = None
    notes: str | None = None


class RaceRead(RaceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    athlete_id: uuid.UUID
    created_at: datetime


class RaceResultCreate(BaseModel):
    race_id: uuid.UUID
    overall_position: int | None = None
    category_position: int | None = None
    finish_time_s: int | None = None
    avg_power: float | None = None
    normalized_power: float | None = None
    tss: float | None = None
    analysis: str | None = None


class RaceResultRead(RaceResultCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class RaceAnalysisCreate(BaseModel):
    race_id: uuid.UUID
    phase: str = Field(default="pre", pattern="^(pre|post)$")
    content: str


class RaceAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    race_id: uuid.UUID
    phase: str
    author: str
    content: str
    created_at: datetime
