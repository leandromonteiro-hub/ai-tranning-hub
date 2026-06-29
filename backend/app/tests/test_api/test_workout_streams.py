"""API tests for GET /workouts/{id}/streams endpoint.

Fixtures (client, auth_headers, session, athlete_id) follow the same pattern
as test_calendar.py — in-memory SQLite with a single athlete, HTTP client
wired to the same DB via dependency override.  The session fixture uses
commit() so seeded data is visible to the handler's independent DB session.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
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
from app.models.workout import WorkoutCompleted, WorkoutStream

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Environment fixture
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
        ath = Athlete(
            email="athlete_a@example.com",
            hashed_password=hash_password("pw12345678"),
            full_name="A",
            role=Role.ATHLETE,
            tenant_id="tenant_a",
        )
        s.add(ath)
        await s.flush()
        ids["A"] = ath.id
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


@pytest_asyncio.fixture
async def client(env):
    return env.client


@pytest_asyncio.fixture
async def athlete_id(env):
    return env.ids["A"]


async def _token(client: AsyncClient, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "pw12345678"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest_asyncio.fixture
async def auth_headers(env, client):
    token = await _token(client, "athlete_a@example.com")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def session(env):
    """Session sharing the same in-memory DB as the HTTP client.

    Callers must call await session.commit() after seeding so the handler's
    independent session can see the data.
    """
    async with env.maker() as s:
        yield s


# ---------------------------------------------------------------------------
# Seed helper
# ---------------------------------------------------------------------------

async def _seed_with_streams(session, aid):
    w = WorkoutCompleted(athlete_id=aid, started_at=datetime(2026, 5, 12, 6, tzinfo=timezone.utc),
                         workout_date=datetime(2026, 5, 12).date(), name="Z2",
                         workout_type=WorkoutType.ENDURANCE, duration_s=10)
    session.add(w)
    await session.flush()
    session.add(WorkoutStream(athlete_id=aid, workout_id=w.id, sample_rate_hz=1.0,
                              time_s=list(range(10)), power=[float(i) for i in range(10)],
                              heart_rate=None, cadence=None, altitude=None))
    await session.flush()
    await session.commit()  # commit so the handler's separate session sees the data
    return w


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_streams_downsampled(client, auth_headers, session, athlete_id):
    w = await _seed_with_streams(session, athlete_id)
    r = await client.get(f"/api/v1/workouts/{w.id}/streams?max_points=5", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["n_points"] == 5
    assert len(body["power"]) == 5
    assert body["power"][0] == 0.5  # média do bucket [0,1]


@pytest.mark.asyncio
async def test_streams_404_for_unknown(client, auth_headers):
    r = await client.get(f"/api/v1/workouts/{uuid.uuid4()}/streams", headers=auth_headers)
    assert r.status_code == 404
