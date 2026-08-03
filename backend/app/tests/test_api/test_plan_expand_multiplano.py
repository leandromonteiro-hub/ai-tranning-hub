"""Expand: regra multi-plano 'prova mais próxima vence' + tss_dropped (spec 2026-08-03)."""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role
from app.models.race import Race
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
    async with maker() as s:
        ath = Athlete(email="a@example.com", hashed_password=hash_password("pw12345678"),
                      full_name="A", role=Role.ATHLETE, tenant_id="ta")
        s.add(ath)
        await s.flush()
        aid = ath.id
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
        yield SimpleNamespace(client=c, maker=maker, aid=aid)
    app.dependency_overrides.clear()
    await engine.dispose()


async def _auth(client):
    r = await client.post("/api/v1/auth/login",
                          data={"username": "a@example.com", "password": "pw12345678"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _make_race(env, name: str, when: date) -> str:
    async with env.maker() as s:
        rc = Race(athlete_id=env.aid, name=name, race_date=when, priority="B")
        s.add(rc)
        await s.flush()
        rid = str(rc.id)
        await s.commit()
    return rid


async def _gen_and_expand(env, headers, name: str, race_iso: str, race_id: str) -> dict:
    r = await env.client.post("/api/v1/plans/generate", json={
        "name": name, "race_date": race_iso, "target_race_id": race_id, "priority": "B",
    }, headers=headers)
    assert r.status_code == 201, r.text
    plan_id = r.json()["id"]
    ex = await env.client.post(f"/api/v1/plans/{plan_id}/expand", headers=headers)
    assert ex.status_code == 201, ex.text
    return ex.json()


async def test_prova_mais_proxima_vence_o_dia(env):
    headers = await _auth(env.client)
    near_date = date.today() + timedelta(days=21)
    far_date = date.today() + timedelta(days=180)
    near = await _make_race(env, "Prova Perto", near_date)
    far = await _make_race(env, "Prova Longe", far_date)

    # Plano da prova distante primeiro, depois o da prova próxima.
    await _gen_and_expand(env, headers, "Plano Longe", far_date.isoformat(), far)
    await _gen_and_expand(env, headers, "Plano Perto", near_date.isoformat(), near)

    async with env.maker() as s:
        rows = (await s.execute(select(WorkoutPlanned).where(
            WorkoutPlanned.athlete_id == env.aid,
            WorkoutPlanned.deleted_at.is_(None),
        ))).scalars().all()
    per_day: dict = {}
    for w in rows:
        per_day.setdefault(w.planned_date, []).append(w)
    # Nunca dois treinos de planos diferentes no mesmo dia.
    assert all(len(v) == 1 for v in per_day.values())


async def test_expand_do_plano_distante_nao_rouba_dias_do_proximo(env):
    headers = await _auth(env.client)
    near_date = date.today() + timedelta(days=21)
    far_date = date.today() + timedelta(days=180)
    near = await _make_race(env, "Perto", near_date)
    far = await _make_race(env, "Longe", far_date)

    await _gen_and_expand(env, headers, "Plano Perto", near_date.isoformat(), near)
    async with env.maker() as s:
        before = {(w.planned_date, w.name) for w in (await s.execute(
            select(WorkoutPlanned).where(WorkoutPlanned.athlete_id == env.aid,
                                         WorkoutPlanned.deleted_at.is_(None)))).scalars().all()}

    await _gen_and_expand(env, headers, "Plano Longe", far_date.isoformat(), far)
    async with env.maker() as s:
        rows = (await s.execute(select(WorkoutPlanned).where(
            WorkoutPlanned.athlete_id == env.aid,
            WorkoutPlanned.deleted_at.is_(None)))).scalars().all()
    after = {(w.planned_date, w.name) for w in rows}
    # Os dias do plano da prova próxima continuam intactos.
    assert before <= after


async def test_expand_responde_tss_dropped(env):
    headers = await _auth(env.client)
    when = date.today() + timedelta(days=60)
    rid = await _make_race(env, "Solo", when)
    result = await _gen_and_expand(env, headers, "Plano Solo", when.isoformat(), rid)
    assert "tss_dropped" in result
    assert result["tss_dropped"] >= 0.0
