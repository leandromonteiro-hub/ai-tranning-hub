"""Training plans, blocks and weeks (periodization persistence)."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin
from app.models.enums import BlockType
from app.models.types import EnumStr


class TrainingPlan(Base, TenantMixin):
    """A periodized plan toward a target race (generated or imported)."""

    __tablename__ = "training_plans"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_race_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("races.id"), nullable=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    race_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_ctl: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_weeks: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(32), default="generated")  # generated/imported
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    blocks: Mapped[list["TrainingBlock"]] = relationship(back_populates="plan")
    weeks: Mapped[list["TrainingWeek"]] = relationship(back_populates="plan")


class TrainingBlock(Base, TenantMixin):
    """A mesocycle block (base/build/peak/taper/recovery) inside a plan."""

    __tablename__ = "training_blocks"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_plans.id"), index=True, nullable=False
    )
    block_type: Mapped[BlockType] = mapped_column(EnumStr(BlockType, 16), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    focus: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[TrainingPlan] = relationship(back_populates="blocks")


class TrainingWeek(Base, TenantMixin):
    """A microcycle week with planned vs executed load."""

    __tablename__ = "training_weeks"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_plans.id"), index=True, nullable=False
    )
    week_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    block_type: Mapped[BlockType] = mapped_column(EnumStr(BlockType, 16), nullable=False)
    planned_tss: Mapped[float] = mapped_column(Float, default=0.0)
    executed_tss: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_recovery_week: Mapped[bool] = mapped_column(Boolean, default=False)
    focus: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[TrainingPlan] = relationship(back_populates="weeks")
