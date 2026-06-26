"""API tests for day-adjustment routes (Task 8).

Routes under test:
  POST   /api/v1/plans/workouts/{id}/adjust          → 201 RecommendationRead (preview)
  POST   /api/v1/plans/workouts/{id}/apply-adjustment → 200 PlannedWorkoutRead
  DELETE /api/v1/plans/workouts/{id}/adjustment       → 200 PlannedWorkoutRead

Coverage:
  1. Past planned date → 409.
  2. Full happy path: adjust → apply → revert.
  3. Multi-tenant isolation: athlete B cannot touch athlete A's workout (404).
"""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role, WorkoutType
from app.models.workout import WorkoutPlanned
from app.services.workout import templates

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixture: two athletes (A and B), shared in-memory SQLite engine
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def env():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    ids: dict[str, object] = {}
    async with maker() as s:
        for key, email, tenant in (
            ("A", "a@example.com", "ta"),
            ("B", "b@example.com", "tb"),
        ):
            ath = Athlete(
                email=email,
                hashed_password=hash_password("pw12345678"),
                full_name=key,
                role=Role.ATHLETE,
                tenant_id=tenant,
            )
            s.add(ath)
            await s.flush()
            ids[key] = ath.id
        await s.commit()

    async def _override_get_db():
        async with maker() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield SimpleNamespace(client=c, maker=maker, ids=ids)
    app.dependency_overrides.clear()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _token(client: AsyncClient, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "pw12345678"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _seed_planned(maker, athlete_id, when: date) -> object:
    """Insert a WorkoutPlanned row directly into the test DB and return its id."""
    w = templates.endurance(300.0)
    w.ftp_watts = 300.0
    async with maker() as s:
        wp = WorkoutPlanned(
            athlete_id=athlete_id,
            created_by=athlete_id,
            planned_date=when,
            name="Z2 base test",
            workout_type=WorkoutType.ENDURANCE,
            structure=w.model_dump(),
        )
        s.add(wp)
        await s.commit()
        return wp.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_adjust_rejects_past_day(env):
    """POST /adjust on a past planned date must return 409."""
    wid = await _seed_planned(env.maker, env.ids["A"], date.today() - timedelta(days=2))
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    r = await env.client.post(f"/api/v1/plans/workouts/{wid}/adjust", headers=h)
    assert r.status_code == 409, r.text


async def test_adjust_then_apply_then_revert(env):
    """Full happy-path: adjust (preview) → apply → revert."""
    wid = await _seed_planned(
        env.maker, env.ids["A"], date.today() + timedelta(days=1)
    )
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}

    # Step 1: generate adjustment preview (201)
    adj = await env.client.post(f"/api/v1/plans/workouts/{wid}/adjust", headers=h)
    assert adj.status_code == 201, adj.text
    rec_id = adj.json()["id"]
    assert rec_id  # a UUID string was returned

    # Step 2: apply the adjustment (200; adjustment column is now populated)
    apply = await env.client.post(
        f"/api/v1/plans/workouts/{wid}/apply-adjustment",
        headers=h,
        json={"recommendation_id": rec_id},
    )
    assert apply.status_code == 200, apply.text
    assert apply.json()["adjustment"] is not None

    # Step 3: revert (200; adjustment column back to None)
    rev = await env.client.delete(
        f"/api/v1/plans/workouts/{wid}/adjustment", headers=h
    )
    assert rev.status_code == 200, rev.text
    assert rev.json()["adjustment"] is None


async def test_apply_adjustment_rejects_mismatched_day(env):
    """A day_adjustment generated for one planned day must not be applied to a
    different planned day (silent cross-day override). Same tenant → 409."""
    wid1 = await _seed_planned(
        env.maker, env.ids["A"], date.today() + timedelta(days=1)
    )
    wid2 = await _seed_planned(
        env.maker, env.ids["A"], date.today() + timedelta(days=3)
    )
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}

    # Generate an adjustment for workout #1
    adj = await env.client.post(f"/api/v1/plans/workouts/{wid1}/adjust", headers=h)
    assert adj.status_code == 201, adj.text
    rec_id = adj.json()["id"]

    # Try to apply workout #1's recommendation onto workout #2 (different day) → 409
    apply = await env.client.post(
        f"/api/v1/plans/workouts/{wid2}/apply-adjustment",
        headers=h,
        json={"recommendation_id": rec_id},
    )
    assert apply.status_code == 409, apply.text


async def test_apply_adjustment_isolated_per_tenant(env):
    """Athlete B cannot adjust or apply on a workout that belongs to athlete A (404)."""
    wid = await _seed_planned(
        env.maker, env.ids["A"], date.today() + timedelta(days=3)
    )
    h_b = {"Authorization": f"Bearer {await _token(env.client, 'b@example.com')}"}

    # B tries to generate an adjustment for A's workout → 404
    r = await env.client.post(f"/api/v1/plans/workouts/{wid}/adjust", headers=h_b)
    assert r.status_code == 404, r.text

    # B tries to apply an adjustment (with a fake rec id) → 404 at workout load
    import uuid
    r2 = await env.client.post(
        f"/api/v1/plans/workouts/{wid}/apply-adjustment",
        headers=h_b,
        json={"recommendation_id": str(uuid.uuid4())},
    )
    assert r2.status_code == 404, r2.text
