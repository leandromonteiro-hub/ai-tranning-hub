"""ST1: WorkoutCompleted and WorkoutPlanned both accept a nullable JSONB extra column."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role
from app.models.workout import WorkoutCompleted, WorkoutPlanned
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


async def test_workout_completed_extra_round_trips(session):
    """WorkoutCompleted.extra stores and retrieves a dict via jsonb."""
    s = session
    athlete = Athlete(
        email="b@example.com",
        hashed_password=hash_password("pw12345678"),
        full_name="B",
        role=Role.ATHLETE,
        tenant_id="tb",
    )
    s.add(athlete)
    await s.flush()

    wc = WorkoutCompleted(
        athlete_id=athlete.id,
        started_at=datetime(2025, 6, 1, 8, 0, tzinfo=timezone.utc),
        workout_date=date(2025, 6, 1),
        extra={"rpe": 7, "pwr_zone_minutes": [10, 5]},
    )
    s.add(wc)
    await s.commit()

    await s.refresh(wc)
    assert wc.extra == {"rpe": 7, "pwr_zone_minutes": [10, 5]}


async def test_workout_planned_extra_round_trips(session):
    """WorkoutPlanned.extra stores and retrieves a dict via jsonb."""
    s = session
    athlete = Athlete(
        email="c@example.com",
        hashed_password=hash_password("pw12345678"),
        full_name="C",
        role=Role.ATHLETE,
        tenant_id="tc",
    )
    s.add(athlete)
    await s.flush()

    wp = WorkoutPlanned(
        athlete_id=athlete.id,
        planned_date=date(2025, 6, 2),
        name="Z2 ride",
        extra={"coach_comments": "Z2"},
    )
    s.add(wp)
    await s.commit()

    await s.refresh(wp)
    assert wp.extra == {"coach_comments": "Z2"}


async def test_extra_nullable(session):
    """extra defaults to None when not provided."""
    s = session
    athlete = Athlete(
        email="d@example.com",
        hashed_password=hash_password("pw12345678"),
        full_name="D",
        role=Role.ATHLETE,
        tenant_id="td",
    )
    s.add(athlete)
    await s.flush()

    wc = WorkoutCompleted(
        athlete_id=athlete.id,
        started_at=datetime(2025, 6, 3, 9, 0, tzinfo=timezone.utc),
        workout_date=date(2025, 6, 3),
        extra=None,
    )
    s.add(wc)
    await s.commit()
    await s.refresh(wc)
    assert wc.extra is None
