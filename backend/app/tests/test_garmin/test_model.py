"""GarminConnection persiste e é athlete-scoped."""
from __future__ import annotations

import pytest

from app.models.enums import GarminConnectionStatus
from app.models.garmin import GarminConnection


@pytest.mark.asyncio
async def test_persist_and_read(session, two_athletes):
    a, _ = two_athletes
    conn = GarminConnection(
        athlete_id=a.id, status=GarminConnectionStatus.CONNECTED,
        encrypted_token="cipher",
    )
    session.add(conn)
    await session.flush()
    assert conn.id is not None
    assert conn.status is GarminConnectionStatus.CONNECTED
    assert conn.created_at is not None  # vem do Base
