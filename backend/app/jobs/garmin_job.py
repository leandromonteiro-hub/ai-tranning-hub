"""Celery job: pull Garmin (activities + wellness) for one athlete."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.tenant import TenantContext
from app.jobs._run import run_async
from app.models.ai import AiRecommendation  # noqa: F401 — used in push/unpush jobs
from app.models.athlete import Athlete
from app.models.enums import GarminConnectionStatus, Role
from app.models.garmin import GarminConnection
from app.repositories.ai_repo import RecommendationRepository
from app.repositories.garmin_repo import GarminConnectionRepository
from app.services.garmin import token_store
from app.services.garmin.client import GarminAuthError, GarminSyncError, RealGarminClient
from app.services.garmin.sync_service import _resume_or_reauth, sync_pull, sync_push, sync_unpush
from app.services.metrics.recompute import recompute_load_metrics
from app.services.workout.model import StructuredWorkout


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


async def _do_push_recommendation(
    rec_id: str,
    athlete_id: str,
    tenant_id: str | None = None,
    *,
    client_factory=RealGarminClient,
    session_factory=AsyncSessionLocal,
) -> dict:
    """Push a recommendation's structured workout to Garmin and persist the workout id."""
    aid = uuid.UUID(athlete_id)
    async with session_factory() as session:
        if not tenant_id:
            ath = await session.get(Athlete, aid)
            tenant_id = ath.tenant_id if ath else ""
        ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)

        rec = await RecommendationRepository(session, ctx).get(uuid.UUID(rec_id))
        if rec is None:
            return {"status": "skipped", "reason": "rec_not_found"}

        if not token_store.is_enabled():
            return {"status": "skipped", "reason": "feature_disabled"}

        conn = await GarminConnectionRepository(session, ctx).get_for_athlete()
        if conn is None or conn.status != GarminConnectionStatus.CONNECTED:
            return {"status": "skipped", "reason": "not_connected"}

        variant = (rec.payload or {}).get("chosen_variant", "ai")
        key = "methodology_workout" if variant == "methodology" else "structured_workout"
        sw_data = (rec.payload or {}).get(key)
        if not sw_data:
            return {"status": "skipped", "reason": "no_structured_workout"}

        if rec.target_date is None:
            return {"status": "skipped", "reason": "no_target_date"}

        sw = StructuredWorkout.model_validate(sw_data)
        try:
            wid = await sync_push(session, ctx, client_factory(), aid, sw, rec.target_date)
        except GarminAuthError:
            await session.commit()  # persist needs_reauth marking made by sync_push
            return {"status": "needs_reauth"}

        # Reassign (not mutate) so SQLAlchemy detects the JSONB change
        rec.payload = {**rec.payload, "garmin_workout_id": wid}
        session.add(rec)
        await session.commit()
        return {"status": "ok", "garmin_workout_id": wid}


async def _do_unpush_recommendation(
    rec_id: str,
    athlete_id: str,
    tenant_id: str | None = None,
    *,
    client_factory=RealGarminClient,
    session_factory=AsyncSessionLocal,
) -> dict:
    """Unschedule a previously pushed workout from Garmin and clear its id from the payload."""
    aid = uuid.UUID(athlete_id)
    async with session_factory() as session:
        if not tenant_id:
            ath = await session.get(Athlete, aid)
            tenant_id = ath.tenant_id if ath else ""
        ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)

        rec = await RecommendationRepository(session, ctx).get(uuid.UUID(rec_id))
        if rec is None:
            return {"status": "skipped", "reason": "rec_not_found"}

        wid = (rec.payload or {}).get("garmin_workout_id")
        if not wid:
            return {"status": "skipped", "reason": "no_garmin_workout_id"}

        if not token_store.is_enabled():
            return {"status": "skipped", "reason": "feature_disabled"}

        conn = await GarminConnectionRepository(session, ctx).get_for_athlete()
        if conn is None or conn.status != GarminConnectionStatus.CONNECTED:
            return {"status": "skipped", "reason": "not_connected"}

        # Resume the token before calling sync_unpush (which does not resume itself)
        client = client_factory()
        try:
            await _resume_or_reauth(session, ctx, client, aid)
            await sync_unpush(session, ctx, client, wid)
        except GarminAuthError:
            await session.commit()  # persist needs_reauth marking
            return {"status": "needs_reauth"}

        # Reassign to trigger SQLAlchemy JSONB change detection
        rec.payload = {k: v for k, v in rec.payload.items() if k != "garmin_workout_id"}
        session.add(rec)
        await session.commit()
        return {"status": "ok"}


def push_recommendation_to_garmin(rec_id: str, athlete_id: str, tenant_id: str | None = None) -> dict:
    """Celery task: push a recommendation's workout to Garmin (registered as 'garmin_push_recommendation')."""
    return run_async(_do_push_recommendation(rec_id, athlete_id, tenant_id))


def unpush_recommendation_from_garmin(rec_id: str, athlete_id: str, tenant_id: str | None = None) -> dict:
    """Celery task: remove a scheduled workout from Garmin (registered as 'garmin_unpush_recommendation')."""
    return run_async(_do_unpush_recommendation(rec_id, athlete_id, tenant_id))


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

    sync_athlete_garmin = celery.task(  # type: ignore[assignment]
        name="garmin_sync",
        autoretry_for=(GarminSyncError,),
        retry_backoff=True,
        max_retries=3,
    )(sync_athlete_garmin)
    beat_sync_all = celery.task(name="garmin_beat_sync_all")(beat_sync_all)  # type: ignore[assignment]
    push_recommendation_to_garmin = celery.task(  # type: ignore[assignment]
        name="garmin_push_recommendation",
        autoretry_for=(GarminSyncError,),
        retry_backoff=True,
        max_retries=3,
    )(push_recommendation_to_garmin)
    unpush_recommendation_from_garmin = celery.task(  # type: ignore[assignment]
        name="garmin_unpush_recommendation",
        autoretry_for=(GarminSyncError,),
        retry_backoff=True,
        max_retries=3,
    )(unpush_recommendation_from_garmin)
except Exception:  # noqa: BLE001 — importable without a broker (tests)
    pass
