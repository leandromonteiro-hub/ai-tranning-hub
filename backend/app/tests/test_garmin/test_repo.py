"""Repositório da conexão Garmin: 1 por atleta, isolado por tenant."""
from __future__ import annotations

import pytest

from app.models.enums import GarminConnectionStatus
from app.repositories.garmin_repo import GarminConnectionRepository
from app.tests.conftest import ctx_for


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent(session, two_athletes):
    a, _ = two_athletes
    repo = GarminConnectionRepository(session, ctx_for(a))
    c1 = await repo.get_or_create()
    c2 = await repo.get_or_create()
    assert c1.id == c2.id
    assert c1.status is GarminConnectionStatus.DISCONNECTED


@pytest.mark.asyncio
async def test_tenant_isolation(session, two_athletes):
    a, b = two_athletes
    repo_a = GarminConnectionRepository(session, ctx_for(a))
    await repo_a.get_or_create()
    repo_b = GarminConnectionRepository(session, ctx_for(b))
    assert await repo_b.get_for_athlete() is None  # B não vê a conexão de A
