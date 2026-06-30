"""sync_pull: importa atividades via pipeline real + upsert de wellness; idempotente."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.enums import GarminConnectionStatus
from app.repositories.garmin_repo import GarminConnectionRepository
from app.repositories.metrics_repo import RecoveryRepository
from app.repositories.workout_repo import WorkoutRepository
from app.services.garmin.fake_client import FakeGarminClient
from app.services.garmin.sync_service import sync_pull
from app.services.garmin.client import GarminAuthError
from app.services.garmin.types import WellnessSnapshot
from app.tests.conftest import ctx_for

# Um FIT mínimo válido é difícil de forjar inline; usamos um CSV de 1 atividade,
# que a pipeline aceita. O FakeGarminClient devolve esses bytes e o sync chama
# import_file com filename ".csv" quando source-format é csv (ver nota no service).
_CSV = (
    b"date,duration_s,distance_m,avg_power,external_id\n"
    b"2026-06-30T06:00:00,3600,30000,200,garmin-act-1\n"
)


def _client():
    snap = WellnessSnapshot(day=date(2026, 6, 30), hrv_ms=62.0, resting_hr=47,
                            sleep_hours=7.0, sleep_score=78.0, body_battery=66.0)
    return FakeGarminClient(
        activities=[("garmin-act-1", datetime(2026, 6, 30, 6, tzinfo=timezone.utc))],
        fit_bytes=_CSV, wellness={date(2026, 6, 30): snap},
    )


@pytest.mark.asyncio
async def test_pull_imports_activity_and_wellness(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    await GarminConnectionRepository(session, ctx).get_or_create()
    res = await sync_pull(session, ctx, _client(), a.id, _activity_ext="csv")
    assert res.activities_imported == 1
    assert res.wellness_days == 1
    rec = await RecoveryRepository(session, ctx).list_recent(date(2026, 6, 1))
    assert rec[0].hrv_ms == 62.0
    assert rec[0].source == "garmin"


@pytest.mark.asyncio
async def test_pull_is_idempotent(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    await GarminConnectionRepository(session, ctx).get_or_create()
    await sync_pull(session, ctx, _client(), a.id, _activity_ext="csv")
    res2 = await sync_pull(session, ctx, _client(), a.id, _activity_ext="csv")
    assert res2.duplicates == 1
    assert res2.activities_imported == 0
    workouts = await WorkoutRepository(session, ctx).list()
    assert len(workouts) == 1  # não duplicou


@pytest.mark.asyncio
async def test_auth_error_marks_needs_reauth(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    await GarminConnectionRepository(session, ctx).get_or_create()
    bad = FakeGarminClient(raise_auth_on_resume=True)
    with pytest.raises(GarminAuthError):
        await sync_pull(session, ctx, bad, a.id)
    conn = await GarminConnectionRepository(session, ctx).get_for_athlete()
    assert conn.status is GarminConnectionStatus.NEEDS_REAUTH
    assert conn.last_error
