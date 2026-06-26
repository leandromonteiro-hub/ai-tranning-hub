import pytest
from app.models.workout import WorkoutPlanned
from app.schemas.planning import PlannedWorkoutRead

pytestmark = pytest.mark.asyncio


async def test_planned_workout_carries_adjustment(session):
    from datetime import date
    import uuid
    w = WorkoutPlanned(
        athlete_id=uuid.uuid4(), planned_date=date(2026, 6, 30),
        name="Sweet Spot", structure={"elements": []},
        adjustment={"structure": {"elements": []}, "tss": 40, "reason": "fadiga alta"},
    )
    session.add(w)
    await session.flush()
    await session.refresh(w)
    assert w.adjustment["reason"] == "fadiga alta"

    read = PlannedWorkoutRead.model_validate(w)
    assert read.adjustment["tss"] == 40
