"""Metrics schemas (load series, FTP, recovery, subjective)."""
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class LoadMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    metric_date: date
    daily_tss: float
    ctl: float
    atl: float
    tsb: float
    monotony: float | None = None
    strain: float | None = None


class FtpCreate(BaseModel):
    ftp_watts: float = Field(gt=0)
    valid_from: date
    method: str | None = None


class FtpRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ftp_watts: float
    valid_from: date
    valid_to: date | None = None
    method: str | None = None


class RecoveryCreate(BaseModel):
    metric_date: date
    hrv_ms: float | None = None
    resting_hr: int | None = None
    sleep_hours: float | None = None
    sleep_score: float | None = None
    recovery_score: float | None = None


class SubjectiveCreate(BaseModel):
    metric_date: date
    rpe: float | None = Field(default=None, ge=0, le=10)
    mood: int | None = Field(default=None, ge=1, le=5)
    fatigue: int | None = Field(default=None, ge=1, le=5)
    motivation: int | None = Field(default=None, ge=1, le=5)
    soreness: int | None = Field(default=None, ge=1, le=5)
    injury_flag: bool = False
    comment: str | None = None
