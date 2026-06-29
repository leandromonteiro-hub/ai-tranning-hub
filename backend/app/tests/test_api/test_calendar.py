"""API tests for GET /calendar aggregator endpoint.

Fixtures (client, auth_headers, session, athlete_id) are defined locally
following the pattern used by sibling test_api tests (test_onboarding,
test_jobs, etc.).  The shared conftest.py does not expose an HTTP client.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
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
from app.models.race import Race
from app.models.workout import WorkoutCompleted, WorkoutPlanned

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Environment fixture: in-memory SQLite with one athlete (A) and a second
# isolation athlete (other).  Overrides get_db so the HTTP client uses the
# same database.
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
            ("A", "athlete_a@example.com", "tenant_a"),
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
# Thin fixtures that expose env's components under the names the brief uses
# ---------------------------------------------------------------------------

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
    """A session that shares the same SQLite in-memory DB as the HTTP client.

    Uses commit() (not just flush()) so that seeded data is visible to the
    HTTP handler's own session, which is created independently by the
    _override_get_db dependency.
    """
    async with env.maker() as s:
        yield s


# ---------------------------------------------------------------------------
# Helper: seed test data
# ---------------------------------------------------------------------------

async def _seed(session, aid):
    session.add(WorkoutPlanned(athlete_id=aid, planned_date=date(2026, 5, 12),
                               name="Z2", workout_type=WorkoutType.ENDURANCE,
                               planned_tss=80, planned_duration_s=3600))
    session.add(WorkoutCompleted(athlete_id=aid, started_at=datetime(2026, 5, 12, 6, tzinfo=timezone.utc),
                                 workout_date=date(2026, 5, 12), name="Z2 feito",
                                 workout_type=WorkoutType.ENDURANCE, duration_s=3600,
                                 distance_m=30000, elevation_gain_m=200, tss=82, kj=900))
    session.add(Race(athlete_id=aid, name="WOS Canastra", race_date=date(2026, 5, 20)))
    await session.commit()  # commit so the HTTP handler's session sees the data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calendar_aggregates_day_and_week(client, auth_headers, session, athlete_id):
    await _seed(session, athlete_id)
    r = await client.get("/api/v1/calendar?start=2026-05-11&end=2026-05-17", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    day = next(d for d in body["days"] if d["date"] == "2026-05-12")
    assert day["planned"][0]["name"] == "Z2"
    assert day["completed"][0]["tss"] == 82
    assert day["races"][0]["name"] == "WOS Canastra"
    assert day["races"][0]["days_until"] == 8
    wk = next(w for w in body["weeks"] if w["week_start"] == "2026-05-11")
    assert wk["total_tss"] == 82
    assert wk["total_distance_m"] == 30000


@pytest.mark.asyncio
async def test_calendar_is_tenant_isolated(client, auth_headers, session, athlete_id):
    other = uuid.uuid4()
    session.add(WorkoutCompleted(athlete_id=other, started_at=datetime(2026, 5, 12, 6, tzinfo=timezone.utc),
                                 workout_date=date(2026, 5, 12), name="de outro",
                                 workout_type=WorkoutType.ENDURANCE, tss=50))
    await session.commit()
    r = await client.get("/api/v1/calendar?start=2026-05-11&end=2026-05-17", headers=auth_headers)
    assert all(not d["completed"] for d in r.json()["days"])  # não vê treino de outro tenant
