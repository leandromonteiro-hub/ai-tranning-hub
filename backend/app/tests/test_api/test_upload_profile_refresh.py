"""POST /imports/upload enqueues the profile-regen job when new workouts land,
and skips enqueuing on pure-duplicate uploads.

After Task 3 the upload route no longer calls generate_and_persist_profile inline;
it enqueues regenerate_profile_task (best-effort). These tests patch that task so
no real broker is hit.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

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
    """New workouts → regenerate_profile_task.delay() called once + profile_task_id set.
    Pure-duplicate upload → no enqueue + profile_task_id is None."""
    async def _noop(*a, **k):
        return None

    # Stub the heavy inline service so the test exercises only the enqueue wiring.
    monkeypatch.setattr(imports_route, "recompute_load_metrics", _noop)

    # Patch the Celery task (best-effort enqueue).
    mock_task = MagicMock()
    mock_task.delay.return_value = MagicMock(id="upload-task-id")
    monkeypatch.setattr(imports_route, "regenerate_profile_task", mock_task)

    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    csv = b"date,duration_s,avg_power\n2026-05-01,3600,200\n"

    r1 = await env.client.post(
        "/api/v1/imports/upload", headers=h,
        files={"files": ("a.csv", csv, "text/csv")},
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert mock_task.delay.call_count == 1  # a new workout landed -> regen enqueued
    assert body1.get("profile_task_id") == "upload-task-id"

    # Same bytes again -> duplicate -> no new workouts -> no enqueue.
    r2 = await env.client.post(
        "/api/v1/imports/upload", headers=h,
        files={"files": ("a.csv", csv, "text/csv")},
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert mock_task.delay.call_count == 1  # still 1 — no extra enqueue on duplicate
    assert body2.get("profile_task_id") is None


async def test_upload_skips_refresh_when_recompute_false(env, monkeypatch):
    """recompute=false → regenerate_profile_task.delay() NOT called at all."""
    mock_task = MagicMock()
    monkeypatch.setattr(imports_route, "regenerate_profile_task", mock_task)

    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    csv = b"date,duration_s,avg_power\n2026-05-02,3600,210\n"
    r = await env.client.post(
        "/api/v1/imports/upload?recompute=false", headers=h,
        files={"files": ("b.csv", csv, "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert mock_task.delay.call_count == 0  # recompute disabled -> no enqueue
