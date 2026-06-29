import uuid
from datetime import date

import pytest

from app.core.tenant import TenantContext
from app.models.enums import Role, WorkoutType
from app.models.workout import WorkoutPlanned
from app.repositories.plan_repo import PlannedWorkoutRepository


def _ctx(aid):
    return TenantContext(athlete_id=aid, tenant_id="t", role=Role.ATHLETE)


@pytest.mark.asyncio
async def test_list_between_filters_by_date_and_tenant(session):
    a, b = uuid.uuid4(), uuid.uuid4()
    for aid, d in [(a, date(2026, 5, 11)), (a, date(2026, 5, 13)), (a, date(2026, 6, 1)), (b, date(2026, 5, 12))]:
        session.add(WorkoutPlanned(athlete_id=aid, planned_date=d, name="T",
                                   workout_type=WorkoutType.ENDURANCE))
    await session.flush()

    repo = PlannedWorkoutRepository(session, _ctx(a))
    rows = await repo.list_between(date(2026, 5, 11), date(2026, 5, 31))

    assert [r.planned_date for r in rows] == [date(2026, 5, 11), date(2026, 5, 13)]  # ordenado, sem 6/1, sem o de B
