"""Admin panel: the feedback feed attributes each feedback to its athlete."""
from __future__ import annotations

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

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client_admin():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        s.add_all([
            Athlete(email="admin@example.com", hashed_password=hash_password("pw12345678"),
                    full_name="Admin", role=Role.ADMIN, tenant_id="tadmin"),
            Athlete(email="a@example.com", hashed_password=hash_password("pw12345678"),
                    full_name="Atleta A", role=Role.ATHLETE, tenant_id="ta"),
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def _login(client, email):
    r = await client.post("/api/v1/auth/login",
                          data={"username": email, "password": "pw12345678"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def test_admin_feedback_includes_athlete_id(client_admin):
    ath = {"Authorization": f"Bearer {await _login(client_admin, 'a@example.com')}"}
    me = (await client_admin.get("/api/v1/athletes/me", headers=ath)).json()
    athlete_id = me["id"]

    rec = await client_admin.post("/api/v1/recommendations", headers=ath,
                                  json={"kind": "daily_workout"})
    assert rec.status_code == 201, rec.text
    rec_id = rec.json()["id"]
    fb = await client_admin.post(f"/api/v1/feedback/{rec_id}", headers=ath,
                                 json={"rating": 5, "made_sense": True, "comment": "ok"})
    assert fb.status_code == 201, fb.text

    adm = {"Authorization": f"Bearer {await _login(client_admin, 'admin@example.com')}"}
    res = await client_admin.get("/api/v1/admin/feedback", headers=adm)
    assert res.status_code == 200, res.text
    items = res.json()
    assert len(items) >= 1
    assert items[0]["athlete_id"] == athlete_id
