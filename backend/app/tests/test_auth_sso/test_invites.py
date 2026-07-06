"""Convites de uso único: geração, validação case-insensitive, consumo, expiração."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.auth import invites

_ALPHABET = set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")


def test_generate_code_format():
    for _ in range(50):
        code = invites.generate_code()
        assert len(code) == 8
        assert set(code) <= _ALPHABET  # sem 0/O/1/I


@pytest.mark.asyncio
async def test_create_and_find_valid_is_case_insensitive(session):
    created = await invites.create_invites(session, created_by=None, count=2)
    assert len(created) == 2
    found = await invites.find_valid(session, created[0].code.lower())
    assert found is not None and found.id == created[0].id


@pytest.mark.asyncio
async def test_consume_makes_code_invalid(session, two_athletes):
    a, _ = two_athletes
    (inv,) = await invites.create_invites(session, created_by=None, count=1)
    assert await invites.consume(session, inv.id, a.id) is True
    assert await invites.find_valid(session, inv.code) is None


@pytest.mark.asyncio
async def test_consume_twice_second_returns_false(session, two_athletes):
    a, b = two_athletes
    (inv,) = await invites.create_invites(session, created_by=None, count=1)
    assert await invites.consume(session, inv.id, a.id) is True
    assert await invites.consume(session, inv.id, b.id) is False


@pytest.mark.asyncio
async def test_expired_code_is_invalid(session):
    (inv,) = await invites.create_invites(session, created_by=None, count=1)
    inv.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await session.flush()
    assert await invites.find_valid(session, inv.code) is None


@pytest.mark.asyncio
async def test_unknown_code_is_invalid(session):
    assert await invites.find_valid(session, "NAOEXIST") is None
