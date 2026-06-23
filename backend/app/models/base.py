"""Declarative base and common mixins (UUID PK, timestamps, soft delete, tenant)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
)


class Base(DeclarativeBase):
    """Shared base: UUID primary key + audit timestamps + soft delete."""

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # Soft delete: NULL means active. Physical DELETE is never used.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Who created the row (athlete/admin id). Nullable for system-created rows.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class TenantMixin:
    """Adds the athlete_id tenant key. Applied to every athlete-scoped table."""

    @declared_attr
    def athlete_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(
            PG_UUID(as_uuid=True),
            ForeignKey("athletes.id"),
            nullable=False,
            index=True,
        )
