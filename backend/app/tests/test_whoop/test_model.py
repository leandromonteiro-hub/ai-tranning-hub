"""A conexão Whoop é uma por atleta, e nunca guarda credencial em claro.

O unique em athlete_id é o que impede duas conexões concorrentes para o mesmo
atleta — cenário em que um refresh invalidaria o token do outro em silêncio.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.enums import WhoopConnectionStatus
from app.models.whoop import WhoopConnection


def test_status_has_no_mfa_state():
    """A Whoop é OAuth2 puro — um estado de MFA aqui seria copiar o Garmin sem motivo."""
    assert {s.value for s in WhoopConnectionStatus} == {
        "CONNECTED", "NEEDS_REAUTH", "DISCONNECTED",
    }


@pytest.mark.asyncio
async def test_one_connection_per_athlete(session, two_athletes):
    a, _ = two_athletes
    session.add(WhoopConnection(athlete_id=a.id))
    await session.flush()

    session.add(WhoopConnection(athlete_id=a.id))
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.asyncio
async def test_defaults_to_disconnected(session, two_athletes):
    a, _ = two_athletes
    conn = WhoopConnection(athlete_id=a.id)
    session.add(conn)
    await session.flush()

    assert conn.status is WhoopConnectionStatus.DISCONNECTED
    assert conn.encrypted_token is None
    assert conn.backfilled_at is None
    assert conn.created_at is not None  # vem do Base
