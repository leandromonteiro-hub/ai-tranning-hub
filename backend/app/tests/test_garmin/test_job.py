"""Garmin sync job: _do_sync wiring with injectable client and session factories."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import hash_password
from app.core.tenant import TenantContext
from app.jobs.garmin_job import _do_sync
from app.models.athlete import Athlete
from app.models.enums import GarminConnectionStatus, Role
from app.repositories.garmin_repo import GarminConnectionRepository
from app.services.garmin.fake_client import FakeGarminClient
from app.services.garmin.types import WellnessSnapshot
from app.tests.conftest import ctx_for


@pytest.mark.asyncio
async def test_do_sync_imports_and_marks_connected(engine):
    """_do_sync with wellness data commits CONNECTED status and returns ok dict."""
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    # Commit athlete + connection so _do_sync's own session can see them.
    async with maker() as s:
        athlete = Athlete(
            email="sync-job@example.com",
            hashed_password=hash_password("pw"),
            full_name="SyncJob",
            role=Role.ATHLETE,
            tenant_id="tenant_sync_job",
        )
        s.add(athlete)
        await s.flush()
        ctx = ctx_for(athlete)
        conn = await GarminConnectionRepository(s, ctx).get_or_create(athlete.id)
        # Limit wellness loop to ~4 days so the test is fast.
        conn.last_sync_at = datetime(2026, 6, 29, 0, tzinfo=timezone.utc)
        await s.commit()
        aid = str(athlete.id)
        tenant_id = athlete.tenant_id

    snap = WellnessSnapshot(
        day=date(2026, 6, 30),
        hrv_ms=55.0,
        resting_hr=48,
        sleep_hours=7.5,
        sleep_score=80.0,
        body_battery=70.0,
    )

    result = await _do_sync(
        aid,
        tenant_id,
        client_factory=lambda: FakeGarminClient(
            activities=[],  # no activity download — avoids FIT parser
            wellness={date(2026, 6, 30): snap},
        ),
        session_factory=maker,
    )

    assert result["status"] == "ok"
    assert result["wellness_days"] >= 1

    # Verify persistence in a fresh session.
    async with maker() as verify:
        ctx2 = TenantContext(
            athlete_id=uuid.UUID(aid), tenant_id=tenant_id, role=Role.ATHLETE
        )
        updated_conn = await GarminConnectionRepository(verify, ctx2).get_for_athlete()
        assert updated_conn is not None
        assert updated_conn.status is GarminConnectionStatus.CONNECTED


@pytest.mark.asyncio
async def test_do_sync_auth_error_returns_needs_reauth(engine):
    """_do_sync commits NEEDS_REAUTH and returns {status: needs_reauth} on GarminAuthError."""
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with maker() as s:
        athlete = Athlete(
            email="sync-job-auth@example.com",
            hashed_password=hash_password("pw"),
            full_name="SyncJobAuth",
            role=Role.ATHLETE,
            tenant_id="tenant_sync_job_auth",
        )
        s.add(athlete)
        await s.flush()
        ctx = ctx_for(athlete)
        await GarminConnectionRepository(s, ctx).get_or_create(athlete.id)
        await s.commit()
        aid = str(athlete.id)
        tenant_id = athlete.tenant_id

    result = await _do_sync(
        aid,
        tenant_id,
        client_factory=lambda: FakeGarminClient(raise_auth_on_resume=True),
        session_factory=maker,
    )

    assert result == {"status": "needs_reauth"}

    # Verify status persisted to DB.
    async with maker() as verify:
        ctx2 = TenantContext(
            athlete_id=uuid.UUID(aid), tenant_id=tenant_id, role=Role.ATHLETE
        )
        updated_conn = await GarminConnectionRepository(verify, ctx2).get_for_athlete()
        assert updated_conn is not None
        assert updated_conn.status is GarminConnectionStatus.NEEDS_REAUTH
