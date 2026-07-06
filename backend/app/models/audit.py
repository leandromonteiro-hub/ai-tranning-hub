"""Immutable audit log of every meaningful operation."""
from __future__ import annotations

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import jsonb


class AuditLog(Base):
    """Append-only audit trail: who did what, on which tenant, from where."""

    __tablename__ = "audit_logs"

    actor_athlete_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), index=True, nullable=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    method: Mapped[str | None] = mapped_column(String(8), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_athlete_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), index=True, nullable=True
    )
    payload_summary: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_code: Mapped[int | None] = mapped_column(nullable=True)
