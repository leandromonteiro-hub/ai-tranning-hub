"""API tests for the async job-status endpoint.

Route under test:
  GET /api/v1/jobs/{task_id}  → 200 JobStatus (state only, no result payload)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_status_returns_state_only(env):
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    fake = MagicMock(state="SUCCESS", result={"secret": "should-not-leak"})
    with patch("app.api.routes.jobs.AsyncResult", return_value=fake):
        resp = await env.client.get("/api/v1/jobs/abc-123", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"task_id": "abc-123", "state": "SUCCESS"}
    assert "result" not in body  # nunca expõe o payload do resultado


@pytest.mark.asyncio
async def test_job_status_requires_auth(env):
    with patch("app.api.routes.jobs.AsyncResult", return_value=MagicMock(state="PENDING")):
        resp = await env.client.get("/api/v1/jobs/abc-123")  # sem header
    assert resp.status_code in (401, 403)
