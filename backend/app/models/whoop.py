"""Vínculo com a Whoop: uma linha por atleta.

Guarda o token OAuth cifrado — nunca credencial do atleta, porque a Whoop é
OAuth2 e a senha jamais passa por nós (diferente do Garmin, que é integração
não-oficial por login). Mais o ciclo de vida da conexão.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin
from app.models.enums import WhoopConnectionStatus


class WhoopConnection(Base, TenantMixin):
    __tablename__ = "whoop_connections"
    __table_args__ = (UniqueConstraint("athlete_id", name="uq_whoop_conn_athlete"),)

    status: Mapped[WhoopConnectionStatus] = mapped_column(
        Enum(WhoopConnectionStatus, native_enum=False, length=32),
        default=WhoopConnectionStatus.DISCONNECTED,
        nullable=False,
    )
    encrypted_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Marca que o backfill de 180 dias já rodou — evita repetir a carga inicial
    # a cada reconexão.
    backfilled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
