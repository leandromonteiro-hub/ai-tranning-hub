"""Training plan schemas."""
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BlockType, WorkoutType


class PlanGenerateRequest(BaseModel):
    name: str
    race_date: date
    target_race_id: uuid.UUID | None = None
    priority: str = Field(default="A", pattern="^[ABC]$")
    start_date: date | None = None


class TrainingWeekRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    week_index: int
    week_start: date
    block_type: BlockType
    planned_tss: float
    executed_tss: float | None = None
    is_recovery_week: bool
    focus: str | None = None


class TrainingBlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    block_type: BlockType
    order_index: int
    start_date: date
    end_date: date
    focus: str | None = None


class TrainingPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    start_date: date
    race_date: date | None = None
    start_ctl: float | None = None
    total_weeks: int
    source: str
    blocks: list[TrainingBlockRead] = []
    weeks: list[TrainingWeekRead] = []


class PlanExpandResult(BaseModel):
    days: int
    tss_total: float
    start: str
    end: str


class PlannedWorkoutRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    planned_date: date
    name: str
    workout_type: WorkoutType
    planned_duration_s: int | None = None
    planned_tss: float | None = None
    description: str | None = None
    structure: dict | None = None
