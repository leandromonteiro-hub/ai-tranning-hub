"""Export wiring tests: _do_push_recommendation, _do_unpush_recommendation, route enqueue.

TDD: this file is written to be RED before the job functions exist, then GREEN
after garmin_job.py and recommendations.py are updated.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import hash_password
from app.core.tenant import TenantContext
from app.jobs.garmin_job import _do_push_recommendation, _do_unpush_recommendation
from app.models.ai import AiRecommendation
from app.models.athlete import Athlete
from app.models.enums import GarminConnectionStatus, Role
from app.models.garmin import GarminConnection
from app.repositories.garmin_repo import GarminConnectionRepository
from app.services.garmin import token_store
from app.services.garmin.fake_client import FakeGarminClient
from app.tests.conftest import ctx_for

pytestmark = pytest.mark.asyncio

# Minimal StructuredWorkout dict accepted by StructuredWorkout.model_validate
_SW_DICT: dict = {
    "name": "Test Push",
    "elements": [{"intensity": "active", "duration_s": 3600, "target": {"type": "open"}}],
}


@pytest_asyncio.fixture
async def env(engine, monkeypatch):
    """Committed athlete + CONNECTED GarminConnection + Fernet key so is_enabled()=True."""
    monkeypatch.setattr(
        token_store.settings,
        "garmin_token_key",
        Fernet.generate_key().decode(),
    )
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        athlete = Athlete(
            email="export-wiring@example.com",
            hashed_password=hash_password("pw"),
            full_name="ExportWiring",
            role=Role.ATHLETE,
            tenant_id="tenant_export",
        )
        s.add(athlete)
        await s.flush()
        # encrypted_token=None → _resume_or_reauth passes {} to client.resume → FakeGarminClient ok
        conn = GarminConnection(
            athlete_id=athlete.id,
            status=GarminConnectionStatus.CONNECTED,
            encrypted_token=None,
        )
        s.add(conn)
        await s.commit()
        aid = str(athlete.id)
        tenant_id = athlete.tenant_id
    return maker, aid, tenant_id


async def _make_rec(maker, aid: str, payload: dict | None, target_date: date | None) -> str:
    """Commit a recommendation and return its str(id)."""
    async with maker() as s:
        rec = AiRecommendation(
            athlete_id=uuid.UUID(aid),
            summary="wiring test",
            target_date=target_date,
            payload=payload,
        )
        s.add(rec)
        await s.commit()
        return str(rec.id)


# ── _do_push_recommendation ───────────────────────────────────────────────────


async def test_do_push_stores_workout_id(env):
    """Happy path: job pushes to Garmin and stores garmin_workout_id in payload."""
    maker, aid, tenant_id = env
    rec_id = await _make_rec(maker, aid, {"structured_workout": _SW_DICT}, date(2026, 7, 1))
    fake = FakeGarminClient()

    result = await _do_push_recommendation(
        rec_id, aid, tenant_id,
        client_factory=lambda: fake,
        session_factory=maker,
    )

    assert result["status"] == "ok"
    wid = result["garmin_workout_id"]
    assert wid  # e.g. "garmin-workout-1"
    assert len(fake.pushed) == 1

    # Verify the id is persisted in a fresh session
    async with maker() as verify:
        refreshed = await verify.get(AiRecommendation, uuid.UUID(rec_id))
        assert refreshed is not None
        assert refreshed.payload["garmin_workout_id"] == wid


async def test_do_push_skips_when_not_connected(env):
    """DISCONNECTED connection → skipped, no workout pushed, no id stored."""
    maker, aid, tenant_id = env
    async with maker() as s:
        ctx = TenantContext(athlete_id=uuid.UUID(aid), tenant_id=tenant_id, role=Role.ATHLETE)
        conn = await GarminConnectionRepository(s, ctx).get_for_athlete()
        conn.status = GarminConnectionStatus.DISCONNECTED
        await s.commit()

    rec_id = await _make_rec(maker, aid, {"structured_workout": _SW_DICT}, date(2026, 7, 1))
    fake = FakeGarminClient()

    result = await _do_push_recommendation(
        rec_id, aid, tenant_id,
        client_factory=lambda: fake,
        session_factory=maker,
    )

    assert result["status"] == "skipped"
    assert len(fake.pushed) == 0

    async with maker() as verify:
        refreshed = await verify.get(AiRecommendation, uuid.UUID(rec_id))
        assert "garmin_workout_id" not in (refreshed.payload or {})


async def test_do_push_skips_without_structured_workout(env):
    """payload without structured_workout key → skipped."""
    maker, aid, tenant_id = env
    rec_id = await _make_rec(maker, aid, {"other": "data"}, date(2026, 7, 1))
    fake = FakeGarminClient()

    result = await _do_push_recommendation(
        rec_id, aid, tenant_id,
        client_factory=lambda: fake,
        session_factory=maker,
    )

    assert result["status"] == "skipped"
    assert len(fake.pushed) == 0


# ── _do_unpush_recommendation ─────────────────────────────────────────────────


async def test_do_unpush_unschedules_and_clears_id(env):
    """Happy path: job unschedules on Garmin and removes garmin_workout_id from payload."""
    maker, aid, tenant_id = env
    rec_id = await _make_rec(
        maker, aid,
        {"structured_workout": _SW_DICT, "garmin_workout_id": "gw-1"},
        date(2026, 7, 1),
    )
    fake = FakeGarminClient()

    result = await _do_unpush_recommendation(
        rec_id, aid, tenant_id,
        client_factory=lambda: fake,
        session_factory=maker,
    )

    assert result["status"] == "ok"
    assert "gw-1" in fake.unscheduled

    async with maker() as verify:
        refreshed = await verify.get(AiRecommendation, uuid.UUID(rec_id))
        assert refreshed is not None
        assert "garmin_workout_id" not in (refreshed.payload or {})


async def test_do_unpush_skips_without_id(env):
    """payload without garmin_workout_id → skipped immediately."""
    maker, aid, tenant_id = env
    rec_id = await _make_rec(maker, aid, {"structured_workout": _SW_DICT}, date(2026, 7, 1))
    fake = FakeGarminClient()

    result = await _do_unpush_recommendation(
        rec_id, aid, tenant_id,
        client_factory=lambda: fake,
        session_factory=maker,
    )

    assert result["status"] == "skipped"
    assert result.get("reason") == "no_garmin_workout_id"
    assert len(fake.unscheduled) == 0


# ── route enqueue ─────────────────────────────────────────────────────────────


async def test_record_decision_accepted_enqueues_push(monkeypatch):
    """POST /recommendations/{id}/decision ACCEPTED → push_recommendation_to_garmin.delay called."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.api.deps import get_tenant
    from app.core.database import get_db
    from app.core.security import hash_password
    from app.main import app
    from app.models import Base

    monkeypatch.setattr(
        token_store.settings,
        "garmin_token_key",
        Fernet.generate_key().decode(),
    )

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with eng.begin() as c:
        await c.run_sync(lambda con: Base.metadata.create_all(con, tables=tables))
    maker = async_sessionmaker(bind=eng, expire_on_commit=False)

    async with maker() as s:
        athlete = Athlete(
            email="route-decision@example.com",
            hashed_password=hash_password("pw12345678"),
            full_name="RouteDecision",
            role=Role.ATHLETE,
            tenant_id="tenant_rd",
        )
        s.add(athlete)
        await s.flush()
        rec = AiRecommendation(
            athlete_id=athlete.id,
            summary="route enqueue test",
            target_date=date(2026, 7, 1),
            payload={"structured_workout": _SW_DICT},
        )
        s.add(rec)
        await s.commit()
        rec_id = str(rec.id)
        ctx = ctx_for(athlete)

    # Track .delay calls with a mock task object
    push_calls: list = []

    class _MockPushTask:
        def delay(self, *args, **kwargs):
            push_calls.append((args, kwargs))

    import app.jobs.garmin_job as garmin_job_module
    monkeypatch.setattr(garmin_job_module, "push_recommendation_to_garmin", _MockPushTask())

    async def _override_get_db():
        async with maker() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_tenant] = lambda: ctx
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post(
                f"/api/v1/recommendations/{rec_id}/decision",
                json={"decision": "ACCEPTED"},
            )
        assert r.status_code == 200, r.text
        assert len(push_calls) == 1, f"expected 1 push delay call, got {push_calls}"
        # First arg should be the rec_id
        assert rec_id in push_calls[0][0]
    finally:
        app.dependency_overrides.clear()
        await eng.dispose()


async def test_record_decision_rejected_with_id_enqueues_unpush(monkeypatch):
    """POST /decision REJECTED with garmin_workout_id → unpush_recommendation_from_garmin.delay."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.api.deps import get_tenant
    from app.core.database import get_db
    from app.core.security import hash_password
    from app.main import app
    from app.models import Base

    monkeypatch.setattr(
        token_store.settings,
        "garmin_token_key",
        Fernet.generate_key().decode(),
    )

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with eng.begin() as c:
        await c.run_sync(lambda con: Base.metadata.create_all(con, tables=tables))
    maker = async_sessionmaker(bind=eng, expire_on_commit=False)

    async with maker() as s:
        athlete = Athlete(
            email="route-reject@example.com",
            hashed_password=hash_password("pw12345678"),
            full_name="RouteReject",
            role=Role.ATHLETE,
            tenant_id="tenant_rr",
        )
        s.add(athlete)
        await s.flush()
        rec = AiRecommendation(
            athlete_id=athlete.id,
            summary="route reject test",
            target_date=date(2026, 7, 1),
            payload={"structured_workout": _SW_DICT, "garmin_workout_id": "gw-42"},
        )
        s.add(rec)
        await s.commit()
        rec_id = str(rec.id)
        ctx = ctx_for(athlete)

    unpush_calls: list = []

    class _MockUnpushTask:
        def delay(self, *args, **kwargs):
            unpush_calls.append((args, kwargs))

    import app.jobs.garmin_job as garmin_job_module
    monkeypatch.setattr(garmin_job_module, "unpush_recommendation_from_garmin", _MockUnpushTask())

    async def _override_get_db():
        async with maker() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_tenant] = lambda: ctx
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post(
                f"/api/v1/recommendations/{rec_id}/decision",
                json={"decision": "REJECTED"},
            )
        assert r.status_code == 200, r.text
        assert len(unpush_calls) == 1, f"expected 1 unpush delay call, got {unpush_calls}"
        assert rec_id in unpush_calls[0][0]
    finally:
        app.dependency_overrides.clear()
        await eng.dispose()
