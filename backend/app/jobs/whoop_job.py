"""Tasks da Whoop: sync de um atleta, backfill inicial e o enfileirador do beat.

O backfill de 180 dias roda uma vez, na conexão. O sync diário usa janela de 3
dias porque a Whoop corrige e completa registros depois de publicá-los.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.tenant import TenantContext
from app.jobs._run import run_async
from app.models.enums import Role, WhoopConnectionStatus
from app.models.whoop import WhoopConnection
from app.services.whoop import token_store
from app.services.whoop.client import WhoopClient
from app.services.whoop.sync_service import sync_athlete
from app.core.logging import get_logger
from app.services.whoop.types import WhoopRateLimited, WhoopSyncError

log = get_logger(__name__)

DAILY_WINDOW_DAYS = 3
BACKFILL_DAYS = 180


async def _do_sync(
    athlete_id: str,
    tenant_id: str,
    days: int,
    mark_backfilled: bool,
    *,
    client_factory=lambda token: WhoopClient(token),
    session_factory=None,
) -> dict:
    """Sincroniza um atleta. As fábricas são injetáveis para o job ser testável.

    O bloco ``except`` não é decoração: sem ele, a marcação de NEEDS_REAUTH feita
    dentro de ``sync_athlete`` é desfeita quando a sessão fecha pelo caminho da
    exceção — a conexão ficaria CONNECTED para sempre e o atleta nunca veria o
    botão de reconectar. Mesmo motivo do commit em ``garmin_job``.
    """
    aid = uuid.UUID(athlete_id)
    ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)
    maker = session_factory or AsyncSessionLocal
    async with maker() as session:
        conn = (await session.execute(
            select(WhoopConnection).where(
                WhoopConnection.athlete_id == aid,
                WhoopConnection.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if conn is None or not conn.encrypted_token:
            return {"skipped": "sem conexão"}

        stored_token = token_store.decrypt(conn.encrypted_token)
        client = client_factory(stored_token)
        try:
            report = await sync_athlete(session, ctx, aid, client=client, days=days)
        except Exception:
            # A Whoop rotaciona o refresh token a cada renovação. Se o sync falhar
            # DEPOIS de uma renovação, descartar o token novo deixa a conexão com
            # um refresh já gasto — e o atleta trava sem jeito de perceber.
            if token_store.is_enabled() and client.token != stored_token:
                conn.encrypted_token = token_store.encrypt(client.token)
            await session.commit()  # persiste NEEDS_REAUTH e/ou o token renovado
            raise

        if mark_backfilled:
            conn.backfilled_at = datetime.now(timezone.utc)
        await session.commit()
        return {"days_seen": report.days_seen, "days_written": report.days_written}


def _run_or_skip_rate_limited(coro) -> dict:
    """Desiste em silêncio no 429 em vez de deixar o autoretry insistir.

    O limite da Whoop reseta por janela de minuto; o backoff do Celery tentaria
    de novo em ~1s, 2s, 4s — cada tentativa é outro 429 queimando cota. Para o
    job diário, esperar o próximo dia é a resposta certa; para o botão manual, o
    atleta clica de novo.
    """
    try:
        return run_async(coro)
    except WhoopRateLimited as exc:
        log.warning("whoop: limite de requisições; pulando (reset em %ss)", exc.retry_after_s)
        return {"skipped": "rate_limited", "retry_after_s": exc.retry_after_s}


def sync_whoop(athlete_id: str, tenant_id: str) -> dict:
    """Task: janela curta, usada pelo beat e pelo botão 'sincronizar agora'."""
    return _run_or_skip_rate_limited(_do_sync(athlete_id, tenant_id, DAILY_WINDOW_DAYS, False))


def backfill_whoop(athlete_id: str, tenant_id: str) -> dict:
    """Task: carga inicial de 180 dias, disparada uma vez na conexão."""
    return _run_or_skip_rate_limited(_do_sync(athlete_id, tenant_id, BACKFILL_DAYS, True))


async def _enqueue_all_connected() -> int:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(WhoopConnection).where(
                WhoopConnection.status == WhoopConnectionStatus.CONNECTED,
                WhoopConnection.deleted_at.is_(None),
            )
        )
        count = 0
        for conn in rows.scalars().all():
            sync_whoop.delay(str(conn.athlete_id), "")  # tenant resolvido no job
            count += 1
        return count


def beat_sync_all() -> int:
    """Beat entry-point: enfileira o sync de cada atleta conectado."""
    return run_async(_enqueue_all_connected())


# Registra com o Celery quando o app estiver disponível (ignorado nos testes).
try:
    from app.jobs.celery_app import celery

    sync_whoop = celery.task(  # type: ignore[assignment]
        name="whoop_sync",
        autoretry_for=(WhoopSyncError,),
        retry_backoff=True,
        max_retries=3,
    )(sync_whoop)
    backfill_whoop = celery.task(  # type: ignore[assignment]
        name="whoop_backfill",
        autoretry_for=(WhoopSyncError,),
        retry_backoff=True,
        max_retries=3,
    )(backfill_whoop)
    beat_sync_all = celery.task(name="whoop_beat_sync_all")(beat_sync_all)  # type: ignore[assignment]
except Exception:  # noqa: BLE001 — importável sem broker (testes)
    pass
