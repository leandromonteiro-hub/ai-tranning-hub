"""Planned and completed workouts, raw streams, intervals and imported files."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin
from app.models.enums import FileFormat, ImportStatus, WorkoutType
from app.models.types import EnumStr, array, jsonb


class ImportedFile(Base, TenantMixin):
    """Every uploaded file, with content hash for deduplication and status."""

    __tablename__ = "imported_files"

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_format: Mapped[FileFormat] = mapped_column(EnumStr(FileFormat, 8), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ImportStatus] = mapped_column(EnumStr(ImportStatus, 16), default=ImportStatus.PENDING)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)  # trainingpeaks/garmin/manual
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)


class WorkoutCompleted(Base, TenantMixin):
    """An executed workout with derived metrics. The athlete's real history."""

    __tablename__ = "workouts_completed"

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    workout_date: Mapped[date] = mapped_column(index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workout_type: Mapped[WorkoutType] = mapped_column(EnumStr(WorkoutType, 16), default=WorkoutType.OTHER)
    sport: Mapped[str] = mapped_column(String(32), default="cycling")

    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    avg_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_cadence: Mapped[float | None] = mapped_column(Float, nullable=True)
    kj: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Derived load metrics (computed against FTP valid on workout_date)
    intensity_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    tss: Mapped[float | None] = mapped_column(Float, nullable=True)
    ftp_used: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Provenance: which imported file produced this row (real data, not inferred)
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("imported_files.id"), nullable=True
    )
    external_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)

    streams: Mapped[list["WorkoutStream"]] = relationship(back_populates="workout")


class WorkoutStream(Base, TenantMixin):
    """Per-second raw streams for a completed workout (stored as arrays).

    For the MVP we store the channels as Postgres arrays on a single row per
    workout. Migration path to TimescaleDB hypertables is documented in
    docs/architecture.md should volume ever require it.
    """

    __tablename__ = "workout_streams"

    workout_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workouts_completed.id"), index=True, nullable=False
    )
    sample_rate_hz: Mapped[float] = mapped_column(Float, default=1.0)
    time_s: Mapped[list[int] | None] = mapped_column(array(Integer), nullable=True)
    power: Mapped[list[float] | None] = mapped_column(array(Float), nullable=True)
    heart_rate: Mapped[list[float] | None] = mapped_column(array(Float), nullable=True)
    cadence: Mapped[list[float] | None] = mapped_column(array(Float), nullable=True)
    altitude: Mapped[list[float] | None] = mapped_column(array(Float), nullable=True)
    speed: Mapped[list[float] | None] = mapped_column(array(Float), nullable=True)

    workout: Mapped[WorkoutCompleted] = relationship(back_populates="streams")


class WorkoutInterval(Base, TenantMixin):
    """Detected or defined intervals within a workout."""

    __tablename__ = "workout_intervals"

    workout_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workouts_completed.id"), index=True, nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    start_s: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[float | None] = mapped_column(Float, nullable=True)


class WorkoutPlanned(Base, TenantMixin):
    """A prescribed workout. Kept separate from executed history."""

    __tablename__ = "workouts_planned"

    planned_date: Mapped[date] = mapped_column(index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    workout_type: Mapped[WorkoutType] = mapped_column(EnumStr(WorkoutType, 16), default=WorkoutType.ENDURANCE)
    planned_duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planned_tss: Mapped[float | None] = mapped_column(Float, nullable=True)
    structure: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)  # interval blocks
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)
    # Optional link to the recommendation that generated this plan (traceability)
    source_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_recommendations.id"), nullable=True
    )
    source_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_plans.id"), nullable=True, index=True
    )
