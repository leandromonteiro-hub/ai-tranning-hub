"""Physiological, load and recovery metrics. FTP history with validity dates."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class FtpHistory(Base, TenantMixin):
    """FTP values with explicit validity ranges. valid_to NULL = current."""

    __tablename__ = "ftp_history"

    ftp_watts: Mapped[float] = mapped_column(Float, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    method: Mapped[str | None] = mapped_column(String(64), nullable=True)  # test/estimate/manual
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)


class LoadMetric(Base, TenantMixin):
    """Daily training-load series: CTL, ATL, TSB, monotony, strain. One row/day."""

    __tablename__ = "load_metrics"
    __table_args__ = (
        UniqueConstraint("athlete_id", "metric_date", name="uq_load_athlete_date"),
    )

    metric_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    daily_tss: Mapped[float] = mapped_column(Float, default=0.0)
    ctl: Mapped[float] = mapped_column(Float, default=0.0)  # chronic / fitness
    atl: Mapped[float] = mapped_column(Float, default=0.0)  # acute / fatigue
    tsb: Mapped[float] = mapped_column(Float, default=0.0)  # form (ctl - atl, prev day)
    monotony: Mapped[float | None] = mapped_column(Float, nullable=True)
    strain: Mapped[float | None] = mapped_column(Float, nullable=True)


class RecoveryMetric(Base, TenantMixin):
    """HRV, resting HR, sleep, recovery score by date."""

    __tablename__ = "recovery_metrics"
    __table_args__ = (
        UniqueConstraint("athlete_id", "metric_date", name="uq_recovery_athlete_date"),
    )

    metric_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    hrv_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    resting_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recovery_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SubjectiveMetric(Base, TenantMixin):
    """Athlete-reported RPE, mood, fatigue, pain, injury, motivation."""

    __tablename__ = "subjective_metrics"
    __table_args__ = (
        UniqueConstraint("athlete_id", "metric_date", name="uq_subjective_athlete_date"),
    )

    metric_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    rpe: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-10
    mood: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    fatigue: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    motivation: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    soreness: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    injury_flag: Mapped[bool] = mapped_column(default=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class BodyMetric(Base, TenantMixin):
    """Weight, BMI and body composition by date."""

    __tablename__ = "body_metrics"

    metric_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    bmi: Mapped[float | None] = mapped_column(Float, nullable=True)


class PowerCurvePoint(Base, TenantMixin):
    """Best mean-maximal power for a given duration over a period."""

    __tablename__ = "power_curve"

    duration_s: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    best_power: Mapped[float] = mapped_column(Float, nullable=False)
    achieved_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_label: Mapped[str | None] = mapped_column(String(64), nullable=True)  # all-time/90d/...
