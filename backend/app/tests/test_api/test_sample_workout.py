"""Sample structured-workout .fit download (for device-import testing)."""
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
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
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
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def _token(client):
    r = await client.post("/api/v1/auth/login",
                          data={"username": "a@example.com", "password": "pw12345678"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def test_sample_fit_returns_interval_workout(client):
    h = {"Authorization": f"Bearer {await _token(client)}"}
    r = await client.get("/api/v1/recommendations/sample.fit?template=sweet_spot&ftp=250", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/octet-stream"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content[8:12] == b".FIT"


async def test_sample_fit_vo2max_template(client):
    h = {"Authorization": f"Bearer {await _token(client)}"}
    r = await client.get("/api/v1/recommendations/sample.fit?template=vo2max", headers=h)
    assert r.status_code == 200, r.text
    assert r.content[8:12] == b".FIT"


async def test_sample_fit_unknown_template_is_400(client):
    h = {"Authorization": f"Bearer {await _token(client)}"}
    r = await client.get("/api/v1/recommendations/sample.fit?template=nope", headers=h)
    assert r.status_code == 400


async def test_sample_fit_requires_auth(client):
    r = await client.get("/api/v1/recommendations/sample.fit?template=sweet_spot")
    assert r.status_code == 401


async def test_sample_zwo_returns_valid_zwift_xml(client):
    import xml.etree.ElementTree as ET
    h = {"Authorization": f"Bearer {await _token(client)}"}
    r = await client.get("/api/v1/recommendations/sample.zwo?template=sweet_spot", headers=h)
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["content-disposition"].endswith('.zwo"')
    root = ET.fromstring(r.content)
    assert root.tag == "workout_file"
    assert root.findtext("sportType") == "bike"
    # native interval grouping, not flattened
    assert len(root.find("workout").findall("IntervalsT")) == 1


async def test_sample_zwo_unknown_template_is_400(client):
    h = {"Authorization": f"Bearer {await _token(client)}"}
    r = await client.get("/api/v1/recommendations/sample.zwo?template=nope", headers=h)
    assert r.status_code == 400
