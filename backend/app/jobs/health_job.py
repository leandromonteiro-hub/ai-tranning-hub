"""Heartbeat do worker e alerta de task falhada (monitor externo).

O ping do heartbeat só sai DEPOIS de run_async ter executado de verdade: é o
mesmo caminho (asyncio.run -> shutdown_default_executor -> thread.start()) que
estourou no incidente de 2026-07-28. Um check externo teria ficado verde.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.monitoring import ping_monitor
from app.jobs._run import run_async

logger = logging.getLogger(__name__)


async def _check_db() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))


def monitoring_heartbeat() -> dict:
    """Beat entry-point: prova que o worker executa task e pinga o monitor."""
    run_async(_check_db())  # falhou aqui => sem ping E task_failure dispara
    pinged = ping_monitor(settings.monitor_heartbeat_url)
    return {"pinged": pinged}


def alert_task_failure(sender=None, task_id=None, exception=None, **kwargs) -> None:
    """Handler do sinal task_failure do Celery. Blindado: nunca levanta.

    Uma exceção aqui mascararia o erro original da task — justamente o que se
    quer enxergar.
    """
    try:
        name = getattr(sender, "name", None) or "unknown"
        ping_monitor(
            settings.monitor_failure_url,
            suffix="/fail",
            body=f"task={name} id={task_id} error={exception!r}",
        )
    except Exception as exc:  # noqa: BLE001 — alerta nunca mascara a falha real
        logger.warning("task_failure alert failed: %r", exc)


# Registra no Celery quando o app estiver disponível (ignorado nos testes).
try:
    from app.jobs.celery_app import celery

    monitoring_heartbeat = celery.task(name="monitoring_heartbeat")(monitoring_heartbeat)  # type: ignore[assignment]
except Exception:  # noqa: BLE001 — importável sem broker (testes)
    pass
