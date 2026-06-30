"""Garmin Connect link: one row per athlete. Holds the encrypted garth token
(never the password) and the connection lifecycle status."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin
from app.models.enums import GarminConnectionStatus


class GarminConnection(Base, TenantMixin):
    __tablename__ = "garmin_connections"
    __table_args__ = (
        UniqueConstraint("athlete_id", name="uq_garmin_conn_athlete"),
    )

    status: Mapped[GarminConnectionStatus] = mapped_column(
        Enum(GarminConnectionStatus, native_enum=False, length=32),
        default=GarminConnectionStatus.DISCONNECTED,
        nullable=False,
    )
    encrypted_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
