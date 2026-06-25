"""POST /imports/upload refreshes the reverse-engineered profile when new
workouts land, and skips it on pure-duplicate uploads."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.api.routes.imports as imports_route
from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role

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
    async with maker() as s:
        s.add(Athlete(email="a@example.com", hashed_password=hash_password("pw12345678"),
                      full_name="A", role=Role.ATHLETE, tenant_id="ta"))
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
        yield SimpleNamespace(client=c)
    app.dependency_overrides.clear()
    await engine.dispose()


async def _token(client, email):
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "pw12345678"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def test_upload_refreshes_profile_only_on_new_workouts(env, monkeypatch):
    calls = {"n": 0}

    async def _spy(*a, **k):
        calls["n"] += 1
        return {}

    async def _noop(*a, **k):
        return None

    # Stub the heavy services so the test exercises only the refresh wiring.
    monkeypatch.setattr(imports_route, "generate_and_persist_profile", _spy)
    monkeypatch.setattr(imports_route, "recompute_load_metrics", _noop)

    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    csv = b"date,duration_s,avg_power\n2026-05-01,3600,200\n"

    r1 = await env.client.post(
        "/api/v1/imports/upload", headers=h,
        files={"files": ("a.csv", csv, "text/csv")},
    )
    assert r1.status_code == 200, r1.text
    assert calls["n"] == 1  # a new workout landed -> profile refreshed

    # Same bytes again -> duplicate -> no new workouts -> no refresh.
    r2 = await env.client.post(
        "/api/v1/imports/upload", headers=h,
        files={"files": ("a.csv", csv, "text/csv")},
    )
    assert r2.status_code == 200, r2.text
    assert calls["n"] == 1


async def test_upload_skips_refresh_when_recompute_false(env, monkeypatch):
    calls = {"n": 0}

    async def _spy(*a, **k):
        calls["n"] += 1
        return {}

    monkeypatch.setattr(imports_route, "generate_and_persist_profile", _spy)

    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    csv = b"date,duration_s,avg_power\n2026-05-02,3600,210\n"
    r = await env.client.post(
        "/api/v1/imports/upload?recompute=false", headers=h,
        files={"files": ("b.csv", csv, "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert calls["n"] == 0  # recompute disabled -> no profile refresh
