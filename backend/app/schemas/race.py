"""Race, result and analysis schemas."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RaceCreate(BaseModel):
    name: str
    race_date: date
    end_date: date | None = None  # último dia (stage races); None = 1 dia
    discipline: str | None = None
    priority: str = Field(default="A", pattern="^[ABC]$")
    location: str | None = None
    distance_km: float | None = None
    elevation_gain_m: float | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _valida_periodo(self):
        if self.end_date is not None:
            if self.end_date < self.race_date:
                raise ValueError("end_date não pode ser antes de race_date")
            if (self.end_date - self.race_date).days > 13:
                raise ValueError("prova não pode ter mais de 14 dias")
        return self


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
