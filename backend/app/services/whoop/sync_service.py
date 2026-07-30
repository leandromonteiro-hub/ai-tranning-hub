"""Orquestra o pull da Whoop. Recebe o client por injeção, então testa offline.

Grava via ``merge_into``, que é onde vive a precedência entre fontes — este
módulo não sabe nada sobre o Garmin.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.models.enums import WhoopConnectionStatus
from app.models.metrics import RecoveryMetric
from app.models.whoop import WhoopConnection
from app.services.recovery.merge import merge_into
from app.services.whoop import token_store
from app.services.whoop.types import WhoopAuthError

log = get_logger(__name__)
SOURCE = "whoop"


@dataclass
class WhoopSyncReport:
    days_seen: int = 0
    days_written: int = 0


async def _get_connection(session: AsyncSession, athlete_id: uuid.UUID) -> WhoopConnection | None:
    return (await session.execute(
        select(WhoopConnection).where(
            WhoopConnection.athlete_id == athlete_id,
            WhoopConnection.deleted_at.is_(None),
        )
    )).scalar_one_or_none()


async def sync_athlete(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    *,
    client,
    days: int,
) -> WhoopSyncReport:
    """Puxa os últimos ``days`` dias e grava em recovery_metrics."""
    conn = await _get_connection(session, athlete_id)
    if conn is None:
        raise WhoopAuthError("atleta não tem conexão Whoop")

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)

    try:
        fetched = client.fetch_days(start, today)
    except WhoopAuthError as exc:
        conn.status = WhoopConnectionStatus.NEEDS_REAUTH
        conn.last_error = str(exc)[:512]
        await session.flush()
        raise

    report = WhoopSyncReport(days_seen=len(fetched))
    for day in fetched:
        # Um dia sem NENHUMA medida não vira linha: linha vazia conta como "dia de
        # recuperação" no cálculo de riqueza de dados do perfil e derruba o score
        # do atleta sem que exista dado nenhum ali.
        if all(getattr(day.snapshot, f.name) is None for f in fields(day.snapshot)):
            continue
        existing = (await session.execute(
            select(RecoveryMetric).where(
                RecoveryMetric.athlete_id == athlete_id,
                RecoveryMetric.metric_date == day.metric_date,
                RecoveryMetric.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if existing is None:
            existing = RecoveryMetric(athlete_id=athlete_id, metric_date=day.metric_date)
            session.add(existing)
        if merge_into(existing, day.snapshot, SOURCE):
            report.days_written += 1

    # O token pode ter sido renovado durante o fetch — persiste o novo.
    if token_store.is_enabled():
        conn.encrypted_token = token_store.encrypt(client.token)
    conn.last_sync_at = datetime.now(timezone.utc)
    conn.last_error = None
    await session.flush()
    log.info(
        "whoop: atleta=%s dias_vistos=%d dias_escritos=%d",
        athlete_id, report.days_seen, report.days_written,
    )
    return report
