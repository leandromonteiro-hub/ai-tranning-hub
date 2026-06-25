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


class FtpPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ftp_watts: float
    valid_from: date
    valid_to: date | None = None
    method: str | None = None


class FormState(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    metric_date: date
    ctl: float
    atl: float
    tsb: float


class AthleteIntelligenceRead(BaseModel):
    """The computed training intelligence surfaced to the athlete dashboard.

    ``twin_seed`` is the reverse-engineered profile blob (intensity_split,
    power_curve_bests, block_summary, ftp_timeline, data_richness); null until
    the analysis has been run.
    """
    twin_seed: dict | None = None
    ftp_history: list[FtpPoint] = []
    form: FormState | None = None
