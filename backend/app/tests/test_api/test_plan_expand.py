"""POST /plans/{id}/expand: rule-based, idempotent, tenant-scoped daily expansion."""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import BlockType, Role
from app.models.metrics import FtpHistory
from app.models.training_plan import TrainingPlan, TrainingWeek
from app.models.workout import WorkoutPlanned

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


async def _token(client, email):
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "pw12345678"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _seed_plan(maker, athlete_id, *, start, race, weeks, ftp=300.0):
    async with maker() as s:
        plan = TrainingPlan(
            athlete_id=athlete_id, name="P", start_date=start,
            race_date=race, total_weeks=len(weeks),
        )
        s.add(plan)
        await s.flush()
        for i, (wstart, block, tss, recov) in enumerate(weeks, start=1):
            s.add(TrainingWeek(
                athlete_id=athlete_id, plan_id=plan.id, week_index=i,
                week_start=wstart, block_type=block, planned_tss=tss,
                is_recovery_week=recov,
            ))
        s.add(FtpHistory(
            athlete_id=athlete_id, ftp_watts=ftp, valid_from=start, valid_to=None,
        ))
        await s.commit()
        return plan.id


async def _count_planned(maker, athlete_id, plan_id):
    async with maker() as s:
        res = await s.execute(
            select(func.count()).select_from(WorkoutPlanned).where(
                WorkoutPlanned.athlete_id == athlete_id,
                WorkoutPlanned.source_plan_id == plan_id,
            )
        )
        return res.scalar_one()


def _two_future_weeks():
    today = date.today()
    return today, today + timedelta(days=13), [
        (today, BlockType.BASE, 500.0, False),
        (today + timedelta(days=7), BlockType.BUILD, 600.0, False),
    ]


async def test_expand_creates_daily_workouts(env):
    start, race, weeks = _two_future_weeks()
    plan_id = await _seed_plan(env.maker, env.ids["A"], start=start, race=race, weeks=weeks)
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    r = await env.client.post(f"/api/v1/plans/{plan_id}/expand", headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["days"] > 0
    assert body["tss_total"] > 0
    assert await _count_planned(env.maker, env.ids["A"], plan_id) == body["days"]


async def test_expand_is_idempotent(env):
    start, race, weeks = _two_future_weeks()
    plan_id = await _seed_plan(env.maker, env.ids["A"], start=start, race=race, weeks=weeks)
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    r1 = await env.client.post(f"/api/v1/plans/{plan_id}/expand", headers=h)
    assert r1.status_code == 201, r1.text
    first = await _count_planned(env.maker, env.ids["A"], plan_id)
    r2 = await env.client.post(f"/api/v1/plans/{plan_id}/expand", headers=h)
    assert r2.status_code == 201, r2.text
    second = await _count_planned(env.maker, env.ids["A"], plan_id)
    assert first == second and first > 0


async def test_expand_is_tenant_isolated(env):
    start, race, weeks = _two_future_weeks()
    plan_id = await _seed_plan(env.maker, env.ids["A"], start=start, race=race, weeks=weeks)
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    await env.client.post(f"/api/v1/plans/{plan_id}/expand", headers=h)
    # Athlete B never expanded anything.
    assert await _count_planned(env.maker, env.ids["B"], plan_id) == 0
    # And B cannot expand A's plan (not found within B's tenant).
    hb = {"Authorization": f"Bearer {await _token(env.client, 'b@example.com')}"}
    rb = await env.client.post(f"/api/v1/plans/{plan_id}/expand", headers=hb)
    assert rb.status_code == 404, rb.text


async def test_list_plan_workouts(env):
    start, race, weeks = _two_future_weeks()
    plan_id = await _seed_plan(env.maker, env.ids["A"], start=start, race=race, weeks=weeks)
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    exp = await env.client.post(f"/api/v1/plans/{plan_id}/expand", headers=h)
    assert exp.status_code == 201, exp.text
    lst = await env.client.get(f"/api/v1/plans/{plan_id}/workouts", headers=h)
    assert lst.status_code == 200, lst.text
    rows = lst.json()
    assert len(rows) == exp.json()["days"]
    assert rows == sorted(rows, key=lambda r: r["planned_date"])
    assert all(r["workout_type"] and r["id"] for r in rows)
    # Athlete B sees none of A's daily workouts.
    hb = {"Authorization": f"Bearer {await _token(env.client, 'b@example.com')}"}
    lst_b = await env.client.get(f"/api/v1/plans/{plan_id}/workouts", headers=hb)
    assert lst_b.status_code == 200 and lst_b.json() == []


async def test_expand_race_in_past_returns_400(env):
    today = date.today()
    past = today - timedelta(days=2)
    weeks = [(today - timedelta(days=9), BlockType.BASE, 500.0, False)]
    plan_id = await _seed_plan(env.maker, env.ids["A"], start=past - timedelta(days=7), race=past, weeks=weeks)
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    r = await env.client.post(f"/api/v1/plans/{plan_id}/expand", headers=h)
    assert r.status_code == 400, r.text
