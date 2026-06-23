"""Anamnese: the athlete profile accepts and returns the enriched fields."""
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
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def _token(client):
    r = await client.post("/api/v1/auth/login", data={"username": "a@example.com", "password": "pw12345678"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def test_profile_accepts_enriched_anamnese_fields(client):
    h = {"Authorization": f"Bearer {await _token(client)}"}
    body = {
        "birth_date": "1990-05-10", "sex": "M", "weight_kg": 72.0, "height_cm": 178.0,
        "max_hr": 188, "resting_hr": 52, "primary_discipline": "XCO", "years_training": 6,
        "goals": "Vencer a maratona regional", "weekly_hours": 8.0, "weekly_days": 4,
        "injury_history": "tendinite no joelho em 2024", "medical_conditions": "nenhuma",
        "has_power_meter": True, "has_hr_monitor": True,
    }
    put = await client.put("/api/v1/athletes/me/profile", headers=h, json=body)
    assert put.status_code == 200, put.text
    got = await client.get("/api/v1/athletes/me/profile", headers=h)
    assert got.status_code == 200, got.text
    p = got.json()
    assert p["goals"] == "Vencer a maratona regional"
    assert p["weekly_hours"] == 8.0 and p["weekly_days"] == 4
    assert p["injury_history"] == "tendinite no joelho em 2024"
    assert p["has_power_meter"] is True and p["has_hr_monitor"] is True
