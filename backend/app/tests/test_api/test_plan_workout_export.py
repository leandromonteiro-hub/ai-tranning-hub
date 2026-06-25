"""Per-day planned-workout export (.zwo/.fit), tenant-scoped."""
from __future__ import annotations

from datetime import date
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
        for key, email, tenant in (("A", "a@example.com", "ta"), ("B", "b@example.com", "tb")):
            ath = Athlete(
                email=email, hashed_password=hash_password("pw12345678"),
                full_name=key, role=Role.ATHLETE, tenant_id=tenant,
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


async def _token(client, email):
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "pw12345678"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _seed_planned(maker, athlete_id):
    w = templates.endurance(300.0)
    w.ftp_watts = 300.0
    async with maker() as s:
        wp = WorkoutPlanned(
            athlete_id=athlete_id, created_by=athlete_id,
            planned_date=date(2026, 7, 1), name="Z2 base",
            workout_type=WorkoutType.ENDURANCE, structure=w.model_dump(),
        )
        s.add(wp)
        await s.commit()
        return wp.id


async def test_export_zwo_and_fit(env):
    wid = await _seed_planned(env.maker, env.ids["A"])
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    for ext in ("zwo", "fit"):
        r = await env.client.get(f"/api/v1/plans/workouts/{wid}/export.{ext}", headers=h)
        assert r.status_code == 200, r.text
        assert "attachment" in r.headers.get("content-disposition", "")
        assert len(r.content) > 0


async def test_export_is_tenant_isolated(env):
    wid = await _seed_planned(env.maker, env.ids["B"])
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    r = await env.client.get(f"/api/v1/plans/workouts/{wid}/export.zwo", headers=h)
    assert r.status_code == 404, r.text
