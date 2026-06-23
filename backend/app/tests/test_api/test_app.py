"""End-to-end API tests via httpx ASGITransport (no network, no lifespan)."""
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


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    # Seed two athletes.
    async with maker() as s:
        s.add_all(
            [
                Athlete(email="a@example.com", hashed_password=hash_password("pw12345678"),
                        full_name="A", role=Role.ATHLETE, tenant_id="ta"),
                Athlete(email="b@example.com", hashed_password=hash_password("pw12345678"),
                        full_name="B", role=Role.ATHLETE, tenant_id="tb"),
            ]
        )
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
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def _login(client, email: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "pw12345678"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_login_and_me(client):
    token = await _login(client, "a@example.com")
    resp = await client.get("/api/v1/athletes/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "a@example.com"


@pytest.mark.asyncio
async def test_workout_crud_and_cross_tenant_isolation(client):
    token_a = await _login(client, "a@example.com")
    token_b = await _login(client, "b@example.com")
    ha = {"Authorization": f"Bearer {token_a}"}
    hb = {"Authorization": f"Bearer {token_b}"}

    create = await client.post(
        "/api/v1/workouts",
        headers=ha,
        json={
            "started_at": "2026-01-01T07:00:00Z",
            "name": "Endurance",
            "workout_type": "ENDURANCE",
            "duration_s": 3600,
            "normalized_power": 200,
        },
    )
    assert create.status_code == 201, create.text
    wid = create.json()["id"]

    # A sees it (explicit range covering the workout date).
    rng = "?start=2025-12-01&end=2026-02-01"
    list_a = await client.get(f"/api/v1/workouts{rng}", headers=ha)
    assert len(list_a.json()) == 1

    # B sees nothing and cannot fetch A's workout by id.
    list_b = await client.get(f"/api/v1/workouts{rng}", headers=hb)
    assert list_b.json() == []
    get_b = await client.get(f"/api/v1/workouts/{wid}", headers=hb)
    assert get_b.status_code == 404


@pytest.mark.asyncio
async def test_race_calendar_and_plan_generation(client):
    from datetime import date, timedelta

    ta = await _login(client, "a@example.com")
    tb = await _login(client, "b@example.com")
    ha = {"Authorization": f"Bearer {ta}"}
    hb = {"Authorization": f"Bearer {tb}"}

    race_date = (date.today() + timedelta(weeks=12)).isoformat()
    race = await client.post(
        "/api/v1/races", headers=ha,
        json={"name": "Copa XCO", "race_date": race_date, "discipline": "XCO", "priority": "A"},
    )
    assert race.status_code == 201, race.text
    race_id = race.json()["id"]

    # B cannot see A's race.
    list_b = await client.get("/api/v1/races", headers=hb)
    assert list_b.json() == []

    # Generate a periodized plan toward the race.
    plan = await client.post(
        "/api/v1/plans/generate", headers=ha,
        json={"name": "Plano Copa XCO", "race_date": race_date,
              "target_race_id": race_id, "priority": "A"},
    )
    assert plan.status_code == 201, plan.text
    body = plan.json()
    assert body["total_weeks"] >= 11
    assert len(body["weeks"]) == body["total_weeks"]
    blocks = {b["block_type"] for b in body["blocks"]}
    assert "TAPER" in blocks and "BASE" in blocks
    # Race week load is reduced (taper).
    race_week = sorted(body["weeks"], key=lambda w: w["week_index"])[-1]
    assert race_week["block_type"] == "TAPER"

    # A pre-race analysis can be attached.
    an = await client.post(
        "/api/v1/races/analyses", headers=ha,
        json={"race_id": race_id, "phase": "pre", "content": "Foco em largada e subidas."},
    )
    assert an.status_code == 201, an.text
    assert an.json()["author"] == "athlete"


@pytest.mark.asyncio
async def test_recommendation_and_feedback_flow(client):
    from datetime import date, timedelta

    token = await _login(client, "a@example.com")
    h = {"Authorization": f"Bearer {token}"}

    # A recent workout so evidence collection runs (exercises enum round-trip).
    recent = (date.today() - timedelta(days=2)).isoformat()
    created = await client.post(
        "/api/v1/workouts", headers=h,
        json={"started_at": f"{recent}T07:00:00Z", "name": "Z2",
              "workout_type": "ENDURANCE", "duration_s": 3600, "normalized_power": 180},
    )
    assert created.status_code == 201, created.text

    # anamnese completa é pré-requisito para gerar recomendações
    await client.put("/api/v1/athletes/me/profile", headers=h, json={
        "birth_date": "1990-05-10", "sex": "M", "weight_kg": 72.0, "height_cm": 178.0,
        "max_hr": 188, "primary_discipline": "XCO", "years_training": 6,
        "goals": "Validação", "weekly_hours": 8.0,
    })
    rec = await client.post("/api/v1/recommendations", headers=h, json={"kind": "daily_workout"})
    assert rec.status_code == 201, rec.text
    body = rec.json()
    # Guardrails ran and a risk level is always present.
    assert body["risk_level"] in {"LOW", "MODERATE", "HIGH"}
    assert body["confidence"] is not None
    # Evidence was collected from the real workout (enum field round-tripped).
    assert len(body["evidence"]) >= 1
    rec_id = body["id"]

    fb = await client.post(
        f"/api/v1/feedback/{rec_id}",
        headers=h,
        json={"rating": 5, "made_sense": True, "comment": "useful"},
    )
    assert fb.status_code == 201, fb.text
    assert fb.json()["rating"] == 5
