"""API tests for async upload enqueue wiring (Task 3).

Route under test:
  POST /api/v1/imports/upload → UploadResponse{files, profile_task_id}

Coverage:
  1. New workouts → profile_regen enqueued, task_id returned.
  2. Zero new workouts → no enqueue, profile_task_id is None.
  3. Broker failure → import succeeds, profile_task_id is None (best-effort).

The pipeline (import_file, recompute_load_metrics) is mocked so the tests
focus on enqueue wiring rather than CSV parsing.  Real pipeline coverage lives
in test_ingestion / test_metrics.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
from app.models.enums import Role


# ---------------------------------------------------------------------------
# Fixture: two athletes (A and B), shared in-memory SQLite engine
# (copied verbatim from test_day_adjustment.py lines 40-95)
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


# ---------------------------------------------------------------------------
# Fake pipeline results
# ---------------------------------------------------------------------------

def _fake_import_result(workouts_created: int):
    """Build a fake import result whose imported_file satisfies ImportedFileRead."""
    imported = SimpleNamespace(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        filename="ride.csv",
        file_format="csv",
        status="COMPLETED",
        rows_imported=workouts_created,
        error_message=None,
        created_at=datetime.now(timezone.utc),
    )
    return SimpleNamespace(imported_file=imported, workouts_created=workouts_created)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_enqueues_profile_regen_and_returns_task_id(env):
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    task = MagicMock(id="task-xyz")
    with patch("app.api.routes.imports.import_file",
               new=AsyncMock(return_value=_fake_import_result(1))), \
         patch("app.api.routes.imports.recompute_load_metrics", new=AsyncMock()), \
         patch("app.api.routes.imports.regenerate_profile_task") as t:
        t.delay.return_value = task
        resp = await env.client.post(
            "/api/v1/imports/upload", headers=h,
            files=[("files", ("ride.csv", b"x", "text/csv"))],
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "files" in body
    assert body["profile_task_id"] == "task-xyz"
    t.delay.assert_called_once()  # enfileirou o regen (não rodou inline)


@pytest.mark.asyncio
async def test_upload_no_new_workouts_does_not_enqueue(env):
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    with patch("app.api.routes.imports.import_file",
               new=AsyncMock(return_value=_fake_import_result(0))), \
         patch("app.api.routes.imports.recompute_load_metrics", new=AsyncMock()), \
         patch("app.api.routes.imports.regenerate_profile_task") as t:
        resp = await env.client.post(
            "/api/v1/imports/upload", headers=h,
            files=[("files", ("ride.csv", b"x", "text/csv"))],
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["profile_task_id"] is None
    t.delay.assert_not_called()  # 0 workouts novos → sem enqueue


@pytest.mark.asyncio
async def test_upload_enqueue_failure_does_not_break_import(env):
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    with patch("app.api.routes.imports.import_file",
               new=AsyncMock(return_value=_fake_import_result(1))), \
         patch("app.api.routes.imports.recompute_load_metrics", new=AsyncMock()), \
         patch("app.api.routes.imports.regenerate_profile_task") as t:
        t.delay.side_effect = RuntimeError("broker down")
        resp = await env.client.post(
            "/api/v1/imports/upload", headers=h,
            files=[("files", ("ride.csv", b"x", "text/csv"))],
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["profile_task_id"] is None  # degrada, import preservado
