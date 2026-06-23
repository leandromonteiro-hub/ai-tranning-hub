"""Athlete and profile schemas."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.enums import Role


class AthleteBase(BaseModel):
    full_name: str
    email: EmailStr


class AthleteRead(AthleteBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: Role
    tenant_id: str
    is_active: bool
    created_at: datetime


class AthleteProfileBase(BaseModel):
    birth_date: date | None = None
    sex: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    max_hr: int | None = None
    resting_hr: int | None = None
    primary_discipline: str | None = None
    years_training: int | None = None
    notes: str | None = None
    goals: str | None = None
    weekly_hours: float | None = None
    weekly_days: int | None = None
    injury_history: str | None = None
    medical_conditions: str | None = None
    has_power_meter: bool = False
    has_hr_monitor: bool = False


class AthleteProfileUpdate(AthleteProfileBase):
    pass


class AthleteProfileRead(AthleteProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    athlete_id: uuid.UUID
