"""Async profile-regeneration job (twin_seed / FTP / power curve / methodology).

Mirrors app.jobs.import_job. A per-athlete Redis lock prevents concurrent
regenerations from racing on FtpHistory/PowerCurvePoint inserts; a second
concurrent task is skipped (the first already recomputes the state)."""
from __future__ import annotations

import uuid

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.jobs._run import run_async
from app.models.enums import Role
from app.services.analysis.profile_service import generate_and_persist_profile

log = get_logger(__name__)

_LOCK_TTL_S = 960  # > celery task_time_limit (900s); auto-expira se o worker morrer


async def _do_regenerate(athlete_id: str, tenant_id: str) -> dict:
    aid = uuid.UUID(athlete_id)
    ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)
    client = aioredis.from_url(settings.redis_url)
    lock = client.lock(f"profile_regen:{athlete_id}", timeout=_LOCK_TTL_S, blocking=False)
    acquired = await lock.acquire()
    if not acquired:
        log.info("profile_regen_skipped_locked", extra={"athlete_id": athlete_id})
        await client.aclose()
        return {"status": "skipped", "reason": "regen already running"}
    try:
        async with AsyncSessionLocal() as session:
            summary = await generate_and_persist_profile(session, ctx, aid)
            await session.commit()
        return {"status": "done", "n_workouts": summary["n_workouts"]}
    finally:
        try:
            await lock.release()
        except Exception:  # noqa: BLE001 — lock pode ter expirado; não mascarar o resultado
            pass
        await client.aclose()


def regenerate_profile_task(athlete_id: str, tenant_id: str) -> dict:
    return run_async(_do_regenerate(athlete_id, tenant_id))


# Register with Celery when the app is available.
try:
    from app.jobs.celery_app import celery

    regenerate_profile_task = celery.task(name="regenerate_profile")(regenerate_profile_task)  # type: ignore[assignment]
except Exception:  # noqa: BLE001 — importable without a running broker (e.g. tests)
    pass
