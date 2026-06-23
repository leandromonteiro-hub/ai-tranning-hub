from datetime import date, timedelta

import pytest

from app.models.enums import BlockType
from app.models.training_plan import TrainingPlan, TrainingWeek
from app.repositories.plan_repo import TrainingWeekRepository
from app.tests.conftest import ctx_for

pytestmark = pytest.mark.asyncio


async def test_block_on_returns_block_for_covering_week(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    plan = TrainingPlan(athlete_id=a.id, created_by=a.id, name="P",
                        start_date=date(2026, 6, 1), total_weeks=1)
    session.add(plan)
    await session.flush()
    monday = date(2026, 6, 1)
    session.add(TrainingWeek(athlete_id=a.id, created_by=a.id, plan_id=plan.id,
                             week_index=1, week_start=monday,
                             block_type=BlockType.BUILD, planned_tss=300.0))
    await session.flush()

    repo = TrainingWeekRepository(session, ctx)
    assert await repo.block_on(monday + timedelta(days=3)) == BlockType.BUILD
    # a date past the week window has no covering week
    assert await repo.block_on(monday + timedelta(days=9)) is None
    # a date before any week
    assert await repo.block_on(monday - timedelta(days=1)) is None


async def test_block_on_is_tenant_isolated(session, two_athletes):
    a, b = two_athletes
    plan = TrainingPlan(athlete_id=a.id, created_by=a.id, name="P",
                        start_date=date(2026, 6, 1), total_weeks=1)
    session.add(plan)
    await session.flush()
    session.add(TrainingWeek(athlete_id=a.id, created_by=a.id, plan_id=plan.id,
                             week_index=1, week_start=date(2026, 6, 1),
                             block_type=BlockType.PEAK, planned_tss=300.0))
    await session.flush()

    # Athlete B must not see athlete A's training week.
    repo_b = TrainingWeekRepository(session, ctx_for(b))
    assert await repo_b.block_on(date(2026, 6, 3)) is None
