"""Celery job: pull Garmin (activities + wellness) for one athlete."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.tenant import TenantContext
from app.jobs._run import run_async
from app.models.athlete import Athlete
from app.models.enums import GarminConnectionStatus, Role
from app.models.garmin import GarminConnection
from app.services.garmin.client import GarminAuthError, RealGarminClient
from app.services.garmin.sync_service import sync_pull
from app.services.metrics.recompute import recompute_load_metrics


async def _do_sync(
    athlete_id: str,
    tenant_id: str | None = None,
    *,
    client_factory=RealGarminClient,
    session_factory=AsyncSessionLocal,
) -> dict:
    """Run sync_pull for one athlete and commit the result.

    The two keyword factories exist purely as dependency-injection seams for
    testing; production callers rely on the defaults.
    """
    aid = uuid.UUID(athlete_id)
    async with session_factory() as session:
        if not tenant_id:
            ath = await session.get(Athlete, aid)
            tenant_id = ath.tenant_id if ath else ""
        ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)
        try:
            result = await sync_pull(session, ctx, client_factory(), aid)
        except GarminAuthError:
            await session.commit()  # persist needs_reauth marking done inside sync_pull
            return {"status": "needs_reauth"}
        await recompute_load_metrics(session, ctx, aid)
        await session.commit()
        return {
            "status": "ok",
            "activities_imported": result.activities_imported,
            "duplicates": result.duplicates,
            "wellness_days": result.wellness_days,
        }


def sync_athlete_garmin(athlete_id: str, tenant_id: str) -> dict:
    """Celery task: pull Garmin data for one athlete (registered as 'garmin_sync')."""
    return run_async(_do_sync(athlete_id, tenant_id))


async def _enqueue_all_connected() -> int:
    """Find all CONNECTED athletes and enqueue their sync tasks."""
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(GarminConnection).where(
                GarminConnection.status == GarminConnectionStatus.CONNECTED,
                GarminConnection.deleted_at.is_(None),
            )
        )
        count = 0
        for conn in rows.scalars().all():
            sync_athlete_garmin.delay(str(conn.athlete_id), "")  # tenant resolved in job
            count += 1
        return count


def beat_sync_all() -> int:
    """Beat entry-point: enqueue a sync for every connected athlete."""
    return run_async(_enqueue_all_connected())


# Register with Celery when the app is available (skipped gracefully in tests).
try:
    from app.jobs.celery_app import celery

    sync_athlete_garmin = celery.task(name="garmin_sync")(sync_athlete_garmin)  # type: ignore[assignment]
    beat_sync_all = celery.task(name="garmin_beat_sync_all")(beat_sync_all)  # type: ignore[assignment]
except Exception:  # noqa: BLE001 — importable without a broker (tests)
    pass
