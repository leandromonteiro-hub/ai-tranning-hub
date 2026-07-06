"""Athlete identity, profile, goals and availability."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin
from app.models.types import EnumStr, jsonb
from app.models.enums import GoalStatus, Role


class Athlete(Base):
    """The principal. Holds credentials, role and the tenant key itself."""

    __tablename__ = "athletes"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Nullable: contas criadas via Google SSO não têm senha.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(EnumStr(Role, 16), default=Role.ATHLETE, nullable=False)
    # tenant_id makes isolation explicit even if athlete ids were ever reused.
    tenant_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Vínculo com a conta Google (sub do ID token). Nullable = sem SSO.
    google_sub: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    # Wizard /bem-vindo concluído. NULL = ainda no onboarding.
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    profile: Mapped["AthleteProfile | None"] = relationship(
        back_populates="athlete", uselist=False
    )


class AthleteProfile(Base, TenantMixin):
    """Physiological and sport profile, one per athlete."""

    __tablename__ = "athlete_profiles"

    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resting_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    primary_discipline: Mapped[str | None] = mapped_column(String(32), nullable=True)  # XCO/XCM/...
    years_training: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    goals: Mapped[str | None] = mapped_column(Text, nullable=True)
    weekly_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    weekly_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    injury_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    medical_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_power_meter: Mapped[bool] = mapped_column(Boolean, default=False)
    has_hr_monitor: Mapped[bool] = mapped_column(Boolean, default=False)
    twin_seed: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)

    athlete: Mapped[Athlete] = relationship(back_populates="profile")


class AthleteGoal(Base, TenantMixin):
    """Short/medium/long term objectives with status and progress."""

    __tablename__ = "athlete_goals"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    horizon: Mapped[str] = mapped_column(String(16), default="medium")  # short/medium/long
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[GoalStatus] = mapped_column(EnumStr(GoalStatus, 16), default=GoalStatus.ACTIVE)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class AthleteAvailability(Base, TenantMixin):
    """Recurring weekly availability and schedule restrictions."""

    __tablename__ = "athlete_availability"

    # day_of_week: 0=Mon .. 6=Sun
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    available_minutes: Mapped[int] = mapped_column(Integer, default=0)
    constraints: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)
