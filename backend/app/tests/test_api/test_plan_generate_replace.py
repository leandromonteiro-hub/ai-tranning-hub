"""POST /plans/generate substitui o plano ativo da mesma prova (spec 2026-08-02)."""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from uuid import UUID

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
from app.models.enums import Role, WorkoutType
from app.models.race import Race
from app.models.training_plan import TrainingPlan
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


async def test_regenerar_substitui_plano_da_mesma_prova(env):
    headers = await _auth(env.client)
    race_date = date.today() + timedelta(days=28)
    async with env.maker() as s:
        rc = Race(athlete_id=env.aid, name="Epic", race_date=race_date, priority="B")
        s.add(rc)
        await s.flush()
        race_id = str(rc.id)
        await s.commit()

    body = {"name": "Plano — Epic", "race_date": race_date.isoformat(),
            "target_race_id": race_id, "priority": "B"}
    r1 = await env.client.post("/api/v1/plans/generate", json=body, headers=headers)
    assert r1.status_code == 201, r1.text
    plan1 = r1.json()["id"]
    plan1_uuid = UUID(plan1)
    ex = await env.client.post(f"/api/v1/plans/{plan1}/expand", headers=headers)
    assert ex.status_code == 201, ex.text

    # Treino PASSADO do plano 1 (histórico) — não pode ser apagado na regeneração.
    async with env.maker() as s:
        s.add(WorkoutPlanned(athlete_id=env.aid, source_plan_id=plan1_uuid,
                             planned_date=date.today() - timedelta(days=1),
                             name="Antigo", workout_type=WorkoutType.ENDURANCE,
                             planned_tss=50, planned_duration_s=3600))
        await s.commit()

    r2 = await env.client.post("/api/v1/plans/generate", json=body, headers=headers)
    assert r2.status_code == 201, r2.text
    plan2 = r2.json()["id"]
    assert plan2 != plan1

    async with env.maker() as s:
        old = (await s.execute(select(TrainingPlan).where(TrainingPlan.id == plan1_uuid))).scalar_one()
        assert old.deleted_at is not None  # arquivado

        rows = (await s.execute(select(WorkoutPlanned).where(
            WorkoutPlanned.source_plan_id == plan1_uuid))).scalars().all()
        # Só sobra o treino passado; os futuros do plano antigo foram apagados.
        assert [w.name for w in rows] == ["Antigo"]


async def test_generate_sem_target_race_nao_arquiva_nada(env):
    headers = await _auth(env.client)
    race_date = date.today() + timedelta(days=28)
    body = {"name": "Plano avulso", "race_date": race_date.isoformat()}
    r1 = await env.client.post("/api/v1/plans/generate", json=body, headers=headers)
    r2 = await env.client.post("/api/v1/plans/generate", json=body, headers=headers)
    assert r1.status_code == 201 and r2.status_code == 201
    async with env.maker() as s:
        plans = (await s.execute(select(TrainingPlan).where(
            TrainingPlan.deleted_at.is_(None)))).scalars().all()
        assert len(plans) == 2  # dois planos ativos, nenhum arquivado
