"""O sync é idempotente e nunca deixa a conexão mentir sobre o próprio estado.

Duas regressões que estes testes travam:
- rodar duas vezes a mesma janela não pode duplicar nem alterar nada na segunda
- token rejeitado tem de virar NEEDS_REAUTH, senão o job tenta para sempre em
  silêncio e o atleta nunca sabe que precisa reconectar
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.enums import WhoopConnectionStatus
from app.models.metrics import RecoveryMetric
from app.models.whoop import WhoopConnection
from app.services.recovery.merge import RecoverySnapshot
from app.services.whoop.fake_client import FakeWhoopClient
from app.services.whoop.sync_service import sync_athlete
from app.services.whoop.types import WhoopAuthError, WhoopDay
from app.tests.conftest import ctx_for


def _days():
    """Dois dias dentro da janela de 3 dias que o sync pede (hoje e ontem)."""
    today = datetime.now(timezone.utc).date()
    return [
        WhoopDay(today - timedelta(days=1),
                 RecoverySnapshot(hrv_ms=61.5, resting_hr=48, sleep_hours=6.0)),
        WhoopDay(today,
                 RecoverySnapshot(hrv_ms=58.0, resting_hr=50, sleep_hours=7.1)),
    ]


async def _conn(session, athlete) -> WhoopConnection:
    c = WhoopConnection(
        athlete_id=athlete.id,
        status=WhoopConnectionStatus.CONNECTED,
        encrypted_token=None,
    )
    session.add(c)
    await session.flush()
    return c


async def _rows(session, athlete_id) -> list[RecoveryMetric]:
    return list((await session.execute(
        select(RecoveryMetric).where(RecoveryMetric.athlete_id == athlete_id)
    )).scalars().all())


@pytest.mark.asyncio
async def test_writes_one_row_per_day(session, two_athletes):
    a, _ = two_athletes
    await _conn(session, a)

    report = await sync_athlete(
        session, ctx_for(a), a.id, client=FakeWhoopClient(_days()), days=3
    )

    rows = await _rows(session, a.id)
    assert report.days_written == 2
    assert len(rows) == 2
    assert all(r.source == "whoop" for r in rows)
    assert {r.hrv_ms for r in rows} == {61.5, 58.0}


@pytest.mark.asyncio
async def test_second_run_changes_nothing(session, two_athletes):
    a, _ = two_athletes
    await _conn(session, a)
    await sync_athlete(session, ctx_for(a), a.id, client=FakeWhoopClient(_days()), days=3)

    report = await sync_athlete(
        session, ctx_for(a), a.id, client=FakeWhoopClient(_days()), days=3
    )

    rows = await _rows(session, a.id)
    assert len(rows) == 2
    assert report.days_written == 0  # nada novo escrito


@pytest.mark.asyncio
async def test_auth_error_marks_needs_reauth(session, two_athletes):
    a, _ = two_athletes
    conn = await _conn(session, a)
    client = FakeWhoopClient([], raise_on_fetch=WhoopAuthError("token revogado"))

    with pytest.raises(WhoopAuthError):
        await sync_athlete(session, ctx_for(a), a.id, client=client, days=3)

    assert conn.status is WhoopConnectionStatus.NEEDS_REAUTH
    assert "token revogado" in (conn.last_error or "")


@pytest.mark.asyncio
async def test_does_not_touch_another_athletes_rows(session, two_athletes):
    a, b = two_athletes
    await _conn(session, a)

    await sync_athlete(session, ctx_for(a), a.id, client=FakeWhoopClient(_days()), days=3)

    assert await _rows(session, b.id) == []


@pytest.mark.asyncio
async def test_asks_for_the_requested_window(session, two_athletes):
    """A janela de 3 dias existe porque a Whoop corrige registros depois de publicar."""
    a, _ = two_athletes
    await _conn(session, a)
    client = FakeWhoopClient(_days())

    await sync_athlete(session, ctx_for(a), a.id, client=client, days=3)

    start, end = client.calls[0]
    assert end == datetime.now(timezone.utc).date()
    assert (end - start) == timedelta(days=2)  # 3 dias inclusivos


@pytest.mark.asyncio
async def test_without_connection_refuses(session, two_athletes):
    a, _ = two_athletes  # sem criar WhoopConnection

    with pytest.raises(WhoopAuthError):
        await sync_athlete(
            session, ctx_for(a), a.id, client=FakeWhoopClient(_days()), days=3
        )
