"""Generate and persist a periodized training plan toward a target race."""
from __future__ import annotations

import math
import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.models.enums import BlockType
from app.models.training_plan import TrainingBlock, TrainingPlan, TrainingWeek
from app.repositories.metrics_repo import LoadMetricRepository
from app.services.planning import periodization

log = get_logger(__name__)


async def generate_plan(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    *,
    race_date: date,
    name: str,
    target_race_id: uuid.UUID | None = None,
    priority: str = "A",
    start_date: date | None = None,
) -> TrainingPlan:
    """Build a week-by-week plan from current state to ``race_date`` and persist it."""
    ctx.assert_can_access(athlete_id)
    start_date = start_date or date.today()
    weeks_to_race = max(1, math.ceil((race_date - start_date).days / 7))

    # Current fitness from the load series (fallback to a conservative default).
    latest = await LoadMetricRepository(session, ctx).latest(athlete_id)
    current_ctl = latest.ctl if latest else 0.0

    planned = periodization.build_plan(current_ctl, weeks_to_race, priority=priority)

    plan = TrainingPlan(
        athlete_id=athlete_id,
        created_by=ctx.athlete_id,
        name=name,
        target_race_id=target_race_id,
        start_date=start_date,
        race_date=race_date,
        start_ctl=current_ctl,
        total_weeks=len(planned),
        source="generated",
    )
    session.add(plan)
    await session.flush()

    # Persist weeks and collapse consecutive same-type weeks into blocks.
    block_start: date | None = None
    block_type: BlockType | None = None
    block_order = 0
    prev_effective_type: BlockType | None = None

    for w in planned:
        week_start = start_date + timedelta(weeks=w.week_index - 1)
        session.add(
            TrainingWeek(
                athlete_id=athlete_id, created_by=ctx.athlete_id, plan_id=plan.id,
                week_index=w.week_index, week_start=week_start,
                block_type=w.block_type, planned_tss=w.planned_weekly_tss,
                is_recovery_week=w.is_recovery_week, focus=w.focus,
            )
        )
        # Recovery weeks belong to the surrounding block for block grouping.
        effective = block_type if (w.is_recovery_week and block_type) else w.block_type
        if effective != prev_effective_type:
            if block_type is not None and block_start is not None:
                _add_block(session, athlete_id, ctx, plan.id, block_type, block_order,
                           block_start, week_start - timedelta(days=1))
                block_order += 1
            block_type = effective
            block_start = week_start
            prev_effective_type = effective

    if block_type is not None and block_start is not None:
        _add_block(session, athlete_id, ctx, plan.id, block_type, block_order,
                   block_start, race_date)

    await session.flush()
    log.info("plan_generated", extra={"weeks": len(planned), "weeks_to_race": weeks_to_race})
    return plan


def _add_block(session, athlete_id, ctx, plan_id, block_type, order, start, end) -> None:
    session.add(
        TrainingBlock(
            athlete_id=athlete_id, created_by=ctx.athlete_id, plan_id=plan_id,
            block_type=block_type, order_index=order,
            start_date=start, end_date=end,
            focus=periodization._FOCUS.get(block_type),
        )
    )
