"""sync_push traduz e envia; sync_unpush remove o agendamento."""
from __future__ import annotations

from datetime import date

import pytest

from app.models.enums import GarminConnectionStatus
from app.repositories.garmin_repo import GarminConnectionRepository
from app.services.garmin.client import GarminAuthError
from app.services.garmin.fake_client import FakeGarminClient
from app.services.garmin.sync_service import sync_push, sync_unpush
from app.services.workout.model import Step, StructuredWorkout, Target
from app.tests.conftest import ctx_for


def _sw():
    return StructuredWorkout(
        name="Endurance 1h", ftp_watts=250.0,
        elements=[Step(intensity="active", duration_s=3600,
                       target=Target(type="power_pct_ftp", low=0.6, high=0.7))],
    )


@pytest.mark.asyncio
async def test_push_translates_and_sends(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    await GarminConnectionRepository(session, ctx).get_or_create()
    fc = FakeGarminClient()
    wid = await sync_push(session, ctx, fc, a.id, _sw(), date(2026, 7, 1))
    assert wid == "garmin-workout-1"
    sent_dict, sent_date = fc.pushed[0]
    assert sent_dict["workoutName"] == "Endurance 1h"
    assert sent_date == date(2026, 7, 1)


@pytest.mark.asyncio
async def test_push_auth_error_marks_needs_reauth(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    conn_repo = GarminConnectionRepository(session, ctx)
    await conn_repo.get_or_create()
    fc = FakeGarminClient(raise_auth_on_push=True)
    with pytest.raises(GarminAuthError):
        await sync_push(session, ctx, fc, a.id, _sw(), date(2026, 7, 1))
    conn = await conn_repo.get_or_create()
    assert conn.status == GarminConnectionStatus.NEEDS_REAUTH
    assert conn.last_error is not None


@pytest.mark.asyncio
async def test_unpush_calls_unschedule(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    fc = FakeGarminClient()
    await sync_unpush(session, ctx, fc, "garmin-workout-9")
    assert "garmin-workout-9" in fc.unscheduled
