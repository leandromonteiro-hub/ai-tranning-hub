"""Job da Whoop: o que fica PERSISTIDO depois que a task termina.

Regressão que estes testes travam (achada em revisão, 2026-07-30): o job marcava
NEEDS_REAUTH dentro do sync e deixava a exceção subir sem commit — o
``async with AsyncSessionLocal()`` fechava a sessão e **desfazia a marcação**. A
conexão ficava CONNECTED para sempre, o card nunca mostrava "Reconectar", e o
atleta parava de receber HRV sem nenhum sinal.

O teste antigo passava porque afirmava sobre o objeto em memória, dentro do
serviço, antes de qualquer fronteira de commit. Estes afirmam sobre o banco, numa
sessão nova — que é onde o atleta e a tela realmente leem.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import hash_password
from app.jobs.whoop_job import _do_sync
from app.models.athlete import Athlete
from app.models.enums import Role, WhoopConnectionStatus
from app.models.metrics import RecoveryMetric
from app.models.whoop import WhoopConnection
from app.services.recovery.merge import RecoverySnapshot
from app.services.whoop import token_store
from app.services.whoop.fake_client import FakeWhoopClient
from app.services.whoop.types import WhoopAuthError, WhoopDay


@pytest.fixture(autouse=True)
def _whoop_key(monkeypatch):
    """O job decifra o token guardado — sem chave, nem chega no que se quer testar."""
    from cryptography.fernet import Fernet

    monkeypatch.setattr(token_store.settings, "whoop_token_key", Fernet.generate_key().decode())


async def _athlete_with_connection(maker) -> tuple[str, str]:
    async with maker() as s:
        athlete = Athlete(
            email=f"whoop-job-{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=hash_password("pw"),
            full_name="WhoopJob",
            role=Role.ATHLETE,
            tenant_id="tenant_whoop_job",
        )
        s.add(athlete)
        await s.flush()
        s.add(WhoopConnection(
            athlete_id=athlete.id,
            status=WhoopConnectionStatus.CONNECTED,
            encrypted_token=token_store.encrypt(
                {"access_token": "at", "refresh_token": "rt", "expires_at": 9_999_999_999}
            ),
        ))
        await s.commit()
        return str(athlete.id), athlete.tenant_id


async def _status(maker, athlete_id: str) -> WhoopConnection:
    async with maker() as s:
        return (await s.execute(
            select(WhoopConnection).where(
                WhoopConnection.athlete_id == uuid.UUID(athlete_id)
            )
        )).scalar_one()


@pytest.mark.asyncio
async def test_auth_error_persists_needs_reauth(engine):
    """Sem commit, a marcação some no rollback e o atleta nunca sabe que caiu."""
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    aid, tenant = await _athlete_with_connection(maker)

    with pytest.raises(WhoopAuthError):
        await _do_sync(
            aid, tenant, 3, False,
            client_factory=lambda _t: FakeWhoopClient(
                [], raise_on_fetch=WhoopAuthError("refresh token revogado")
            ),
            session_factory=maker,
        )

    conn = await _status(maker, aid)
    assert conn.status is WhoopConnectionStatus.NEEDS_REAUTH
    assert "revogado" in (conn.last_error or "")


@pytest.mark.asyncio
async def test_successful_sync_persists_rows_and_timestamp(engine):
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    aid, tenant = await _athlete_with_connection(maker)
    today = datetime.now(timezone.utc).date()
    days = [WhoopDay(today, RecoverySnapshot(hrv_ms=61.5, sleep_hours=6.0))]

    result = await _do_sync(
        aid, tenant, 3, False,
        client_factory=lambda _t: FakeWhoopClient(days),
        session_factory=maker,
    )

    assert result["days_written"] == 1
    async with maker() as s:
        rows = (await s.execute(
            select(RecoveryMetric).where(
                RecoveryMetric.athlete_id == uuid.UUID(aid)
            )
        )).scalars().all()
    assert len(rows) == 1
    assert rows[0].source == "whoop"
    assert (await _status(maker, aid)).last_sync_at is not None


@pytest.mark.asyncio
async def test_backfill_marks_backfilled_at(engine):
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    aid, tenant = await _athlete_with_connection(maker)

    await _do_sync(
        aid, tenant, 180, True,
        client_factory=lambda _t: FakeWhoopClient([]),
        session_factory=maker,
    )

    assert (await _status(maker, aid)).backfilled_at is not None


@pytest.mark.asyncio
async def test_without_token_skips_without_touching_the_connection(engine):
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    aid, tenant = await _athlete_with_connection(maker)
    async with maker() as s:
        conn = (await s.execute(
            select(WhoopConnection).where(
                WhoopConnection.athlete_id == uuid.UUID(aid)
            )
        )).scalar_one()
        conn.encrypted_token = None
        await s.commit()

    result = await _do_sync(
        aid, tenant, 3, False,
        client_factory=lambda _t: FakeWhoopClient([]),
        session_factory=maker,
    )

    assert result == {"skipped": "sem conexão"}
    assert (await _status(maker, aid)).status is WhoopConnectionStatus.CONNECTED
