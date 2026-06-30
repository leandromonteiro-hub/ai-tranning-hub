"""Orchestrates Garmin pull/push. Receives the GarminClient by injection so the
whole flow is testable offline. Reuses ingestion_service for activities and
RecoveryMetric for wellness."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.models.enums import GarminConnectionStatus
from app.models.garmin import GarminConnection
from app.models.metrics import RecoveryMetric
from app.repositories.garmin_repo import GarminConnectionRepository
from app.repositories.metrics_repo import RecoveryRepository
from app.services.garmin import token_store
from app.services.garmin.client import GarminAuthError, GarminClient, GarminSyncError
from app.services.ingestion.ingestion_service import import_file
from app.services.workout.model import StructuredWorkout

log = get_logger(__name__)

_PULL_MARGIN_DAYS = 2
_FIRST_SYNC_BACKFILL_DAYS = 60


@dataclass
class PullResult:
    activities_imported: int
    duplicates: int
    wellness_days: int


async def _mark_reauth(repo: GarminConnectionRepository, conn: GarminConnection, message: str) -> None:
    conn.status = GarminConnectionStatus.NEEDS_REAUTH
    conn.last_error = message[:512]
    await repo.session.flush()


def _since(conn) -> date:
    if conn.last_sync_at:
        base = conn.last_sync_at.date()
    else:
        base = datetime.now(timezone.utc).date() - timedelta(days=_FIRST_SYNC_BACKFILL_DAYS)
    return base - timedelta(days=_PULL_MARGIN_DAYS)


async def sync_pull(
    session: AsyncSession,
    ctx: TenantContext,
    client: GarminClient,
    athlete_id: uuid.UUID,
    *,
    _activity_ext: str = "fit",
) -> PullResult:
    conn_repo = GarminConnectionRepository(session, ctx)
    conn = await conn_repo.get_or_create(athlete_id)
    rec_repo = RecoveryRepository(session, ctx)

    try:
        token = token_store.decrypt(conn.encrypted_token) if conn.encrypted_token else {}
        client.resume(token)
    except GarminAuthError as exc:
        await _mark_reauth(conn_repo, conn, str(exc))
        raise

    since = _since(conn)

    imported = 0
    duplicates = 0
    try:
        for ref in client.list_activities(since):
            try:
                data = client.download_activity_fit(ref.activity_id)
                result = await import_file(
                    session, ctx, athlete_id,
                    filename=f"{ref.activity_id}.{_activity_ext}",
                    data=data, source="garmin",
                )
                imported += result.workouts_created
                duplicates += result.duplicates_skipped
            except GarminSyncError as exc:
                log.warning("garmin: skipping activity %s — %s", ref.activity_id, exc)
                continue
    except GarminAuthError as exc:
        await _mark_reauth(conn_repo, conn, str(exc))
        raise

    wellness_days = 0
    day = since
    today = datetime.now(timezone.utc).date()
    try:
        while day <= today:
            snap = client.get_wellness(day)
            if any((snap.hrv_ms, snap.resting_hr, snap.sleep_hours,
                    snap.sleep_score, snap.body_battery)):
                existing = await rec_repo.get_for_date(day, athlete_id)
                if existing is None:
                    existing = RecoveryMetric(athlete_id=athlete_id, metric_date=day)
                    await rec_repo.add(existing)
                existing.hrv_ms = snap.hrv_ms
                existing.resting_hr = snap.resting_hr
                existing.sleep_hours = snap.sleep_hours
                existing.sleep_score = snap.sleep_score
                existing.recovery_score = snap.body_battery
                existing.source = "garmin"
                wellness_days += 1
            day += timedelta(days=1)
    except GarminAuthError as exc:
        await _mark_reauth(conn_repo, conn, str(exc))
        raise

    new_token = client.current_token()
    if new_token and token_store.is_enabled():
        conn.encrypted_token = token_store.encrypt(new_token)
    conn.status = GarminConnectionStatus.CONNECTED
    conn.last_sync_at = datetime.now(timezone.utc)
    conn.last_error = None
    await session.flush()

    return PullResult(imported, duplicates, wellness_days)


async def _resume_or_reauth(session, ctx, client, athlete_id):
    conn_repo = GarminConnectionRepository(session, ctx)
    conn = await conn_repo.get_or_create(athlete_id)
    try:
        token = token_store.decrypt(conn.encrypted_token) if conn.encrypted_token else {}
        client.resume(token)
    except GarminAuthError as exc:
        await _mark_reauth(conn_repo, conn, str(exc))
        raise
    return conn, conn_repo


async def sync_push(session, ctx, client, athlete_id, sw: StructuredWorkout,
                    schedule_date: date) -> str:
    conn, conn_repo = await _resume_or_reauth(session, ctx, client, athlete_id)
    try:
        wid = client.push_workout(sw, schedule_date)
    except GarminAuthError as exc:
        await _mark_reauth(conn_repo, conn, str(exc))
        raise
    new_token = client.current_token()
    if new_token and token_store.is_enabled():
        conn.encrypted_token = token_store.encrypt(new_token)
    await session.flush()
    return wid


async def sync_unpush(session, ctx, client, garmin_workout_id: str) -> None:
    client.unschedule_workout(garmin_workout_id)
