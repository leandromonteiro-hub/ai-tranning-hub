# backend/app/tests/test_api/test_workout_export.py
from datetime import date

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
from app.models.metrics import FtpHistory

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client_with_ftp():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        a = Athlete(email="a@example.com", hashed_password=hash_password("pw12345678"),
                    full_name="A", role=Role.ATHLETE, tenant_id="ta")
        b = Athlete(email="b@example.com", hashed_password=hash_password("pw12345678"),
                    full_name="B", role=Role.ATHLETE, tenant_id="tb")
        s.add_all([a, b])
        await s.flush()
        s.add(FtpHistory(athlete_id=a.id, created_by=a.id,
                         ftp_watts=250.0, valid_from=date(2026, 1, 1)))
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


async def test_export_fit_returns_file_for_owner_and_isolates_others(client_with_ftp):
    ha = {"Authorization": f"Bearer {await _login(client_with_ftp, 'a@example.com')}"}
    hb = {"Authorization": f"Bearer {await _login(client_with_ftp, 'b@example.com')}"}

    rec = await client_with_ftp.post("/api/v1/recommendations", headers=ha,
                                     json={"kind": "daily_workout"})
    assert rec.status_code == 201, rec.text
    rec_id = rec.json()["id"]

    ok = await client_with_ftp.get(f"/api/v1/recommendations/{rec_id}/export.fit", headers=ha)
    assert ok.status_code == 200, ok.text
    assert ok.headers["content-type"] == "application/octet-stream"
    assert ok.content[8:12] == b".FIT"  # FIT header magic

    cross = await client_with_ftp.get(f"/api/v1/recommendations/{rec_id}/export.fit", headers=hb)
    assert cross.status_code == 404


async def test_export_fit_404_when_recommendation_has_no_structured_workout(client_with_ftp):
    hb = {"Authorization": f"Bearer {await _login(client_with_ftp, 'b@example.com')}"}
    rec = await client_with_ftp.post("/api/v1/recommendations", headers=hb, json={"kind": "daily_workout"})
    assert rec.status_code == 201, rec.text
    rec_id = rec.json()["id"]
    resp = await client_with_ftp.get(f"/api/v1/recommendations/{rec_id}/export.fit", headers=hb)
    assert resp.status_code == 404
