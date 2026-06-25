"""GET /athletes/me/intelligence: twin_seed + FTP timeline + form, tenant-scoped."""
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
from app.models.athlete import Athlete, AthleteProfile
from app.models.enums import Role
from app.models.metrics import FtpHistory, LoadMetric

pytestmark = pytest.mark.asyncio

_TWIN = {
    "intensity_split": {"label": "pyramidal", "z1_pct": 0.7, "z2_pct": 0.27, "z3_pct": 0.03},
    "power_curve_bests": {"5 s": 1227.0, "20 min": 331.0},
    "data_richness": {"score": 0.91},
}


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
        # Only athlete A has computed intelligence.
        a = ids["A"]
        s.add(AthleteProfile(athlete_id=a, created_by=a, twin_seed=_TWIN))
        s.add(FtpHistory(athlete_id=a, ftp_watts=281.0, valid_from=date(2026, 1, 1),
                         valid_to=date(2026, 3, 31), method="estimate_pc20"))
        s.add(FtpHistory(athlete_id=a, ftp_watts=297.0, valid_from=date(2026, 4, 1),
                         method="estimate_pc20"))
        s.add(LoadMetric(athlete_id=a, metric_date=date(2026, 6, 24), ctl=85.2, atl=84.0, tsb=-9.7))
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
        yield SimpleNamespace(client=c, ids=ids)
    app.dependency_overrides.clear()
    await engine.dispose()


async def _token(client, email):
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "pw12345678"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def test_intelligence_returns_computed_profile(env):
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    r = await env.client.get("/api/v1/athletes/me/intelligence", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["twin_seed"]["intensity_split"]["label"] == "pyramidal"
    assert len(body["ftp_history"]) == 2
    assert body["ftp_history"][-1]["ftp_watts"] == 297.0  # ordered by valid_from
    assert body["form"]["ctl"] == 85.2 and body["form"]["tsb"] == -9.7


async def test_intelligence_empty_and_isolated(env):
    # Athlete B has no profile/ftp/load -> graceful empty payload (isolation).
    h = {"Authorization": f"Bearer {await _token(env.client, 'b@example.com')}"}
    r = await env.client.get("/api/v1/athletes/me/intelligence", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["twin_seed"] is None
    assert body["ftp_history"] == []
    assert body["form"] is None
