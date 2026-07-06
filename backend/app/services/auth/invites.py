"""Geração/validação/consumo de códigos de convite (uso único)."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invite import InviteCode

# Sem 0/O/1/I — códigos digitáveis sem ambiguidade.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


async def create_invites(
    session: AsyncSession, created_by: uuid.UUID | None, count: int
) -> list[InviteCode]:
    out = [InviteCode(code=generate_code(), created_by=created_by) for _ in range(count)]
    session.add_all(out)
    await session.flush()
    return out


async def find_valid(session: AsyncSession, code: str) -> InviteCode | None:
    stmt = select(InviteCode).where(
        InviteCode.code == code.strip().upper(),
        InviteCode.used_at.is_(None),
        InviteCode.deleted_at.is_(None),
    )
    inv = (await session.execute(stmt)).scalar_one_or_none()
    if inv is None:
        return None
    if inv.expires_at is not None:
        expires = inv.expires_at
        if expires.tzinfo is None:  # SQLite strips tzinfo; treat as UTC
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            return None
    return inv


def consume(invite: InviteCode, athlete_id: uuid.UUID) -> None:
    invite.used_by_athlete_id = athlete_id
    invite.used_at = datetime.now(timezone.utc)
