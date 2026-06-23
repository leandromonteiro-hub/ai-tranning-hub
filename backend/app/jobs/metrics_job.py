"""Async job to recompute an athlete's load series."""
from __future__ import annotations

import uuid

from app.core.database import AsyncSessionLocal
from app.core.tenant import TenantContext
from app.jobs._run import run_async
from app.models.enums import Role
from app.services.metrics.recompute import recompute_load_metrics


async def _do_recompute(athlete_id: str, tenant_id: str) -> dict:
    aid = uuid.UUID(athlete_id)
    ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)
    async with AsyncSessionLocal() as session:
        days = await recompute_load_metrics(session, ctx, aid)
        await session.commit()
        return {"days_written": days}


def recompute_metrics_task(athlete_id: str, tenant_id: str) -> dict:
    return run_async(_do_recompute(athlete_id, tenant_id))


try:
    from app.jobs.celery_app import celery

    recompute_metrics_task = celery.task(name="recompute_metrics")(recompute_metrics_task)  # type: ignore[assignment]
except Exception:  # noqa: BLE001
    pass
