"""ST1: WorkoutPlanned accepts a nullable source_plan_id FK to training_plans."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role
from app.models.training_plan import TrainingPlan
from app.models.workout import WorkoutPlanned
from app.core.security import hash_password

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session():
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
        yield s
    await engine.dispose()


async def test_source_plan_id_round_trips(session):
    """WorkoutPlanned.source_plan_id stores and retrieves the FK UUID."""
    s = session
    athlete = Athlete(
        email="plan_a@example.com",
        hashed_password=hash_password("pw12345678"),
        full_name="Plan A",
        role=Role.ATHLETE,
        tenant_id="t_plan_a",
    )
    s.add(athlete)
    await s.flush()

    plan = TrainingPlan(
        athlete_id=athlete.id,
        name="Base Build 12w",
        start_date=date(2026, 1, 1),
        total_weeks=12,
    )
    s.add(plan)
    await s.flush()

    wp = WorkoutPlanned(
        athlete_id=athlete.id,
        planned_date=date(2026, 1, 6),
        name="Z2 Long Ride",
        source_plan_id=plan.id,
    )
    s.add(wp)
    await s.commit()

    await s.refresh(wp)
    assert wp.source_plan_id == plan.id


async def test_source_plan_id_nullable(session):
    """WorkoutPlanned.source_plan_id defaults to None when not provided."""
    s = session
    athlete = Athlete(
        email="plan_b@example.com",
        hashed_password=hash_password("pw12345678"),
        full_name="Plan B",
        role=Role.ATHLETE,
        tenant_id="t_plan_b",
    )
    s.add(athlete)
    await s.flush()

    wp = WorkoutPlanned(
        athlete_id=athlete.id,
        planned_date=date(2026, 1, 7),
        name="Threshold Intervals",
    )
    s.add(wp)
    await s.commit()

    await s.refresh(wp)
    assert wp.source_plan_id is None
