"""Onboarding state via /auth/me + complete-onboarding; CRUD admin de convites."""
from __future__ import annotations

from datetime import datetime, timezone

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


@pytest_asyncio.fixture
async def client_and_maker():
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
        s.add_all([
            Athlete(email="novo@x.com", hashed_password=hash_password("pw12345678"),
                    full_name="Novo", role=Role.ATHLETE, tenant_id="tn"),
            Athlete(email="antigo@x.com", hashed_password=hash_password("pw12345678"),
                    full_name="Antigo", role=Role.ATHLETE, tenant_id="tv",
                    onboarding_completed_at=datetime.now(timezone.utc)),
            Athlete(email="admin@x.com", hashed_password=hash_password("pw12345678"),
                    full_name="Admin", role=Role.ADMIN, tenant_id="tadm",
                    onboarding_completed_at=datetime.now(timezone.utc)),
        ])
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, maker
    app.dependency_overrides.clear()
    await engine.dispose()


async def _login(client, email: str) -> dict:
    r = await client.post("/api/v1/auth/login",
                          data={"username": email, "password": "pw12345678"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_me_reports_onboarding_state_and_complete_is_idempotent(client_and_maker):
    client, _ = client_and_maker
    h = await _login(client, "novo@x.com")
    assert (await client.get("/api/v1/auth/me", headers=h)).json()["onboarding_completed"] is False
    assert (await client.post("/api/v1/auth/me/complete-onboarding", headers=h)).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=h)).json()["onboarding_completed"] is True
    # idempotente
    assert (await client.post("/api/v1/auth/me/complete-onboarding", headers=h)).status_code == 204

    h2 = await _login(client, "antigo@x.com")
    assert (await client.get("/api/v1/auth/me", headers=h2)).json()["onboarding_completed"] is True


@pytest.mark.asyncio
async def test_admin_creates_and_lists_invites(client_and_maker):
    client, _ = client_and_maker
    h = await _login(client, "admin@x.com")
    r = await client.post("/api/v1/admin/invites", json={"count": 3}, headers=h)
    assert r.status_code == 201
    codes = [i["code"] for i in r.json()]
    assert len(codes) == 3 and all(len(c) == 8 for c in codes)
    listed = (await client.get("/api/v1/admin/invites", headers=h)).json()
    assert {i["code"] for i in listed} >= set(codes)
    assert all(i["used_by_email"] is None for i in listed if i["code"] in codes)


@pytest.mark.asyncio
async def test_invites_routes_are_admin_gated_and_count_capped(client_and_maker):
    client, _ = client_and_maker
    h = await _login(client, "novo@x.com")
    assert (await client.post("/api/v1/admin/invites", json={"count": 1}, headers=h)).status_code == 403
    hadm = await _login(client, "admin@x.com")
    assert (await client.post("/api/v1/admin/invites", json={"count": 51}, headers=hadm)).status_code == 422
