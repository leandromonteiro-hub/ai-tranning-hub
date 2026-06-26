"""Integration test for generate_day_adjustment — mirrors test_recommender_structured.py."""
from datetime import date, timedelta

import pytest

from app.models.enums import RecommendationDecision
from app.models.workout import WorkoutPlanned
from app.services.ai.recommender import generate_day_adjustment
from app.tests.conftest import ctx_for

pytestmark = pytest.mark.asyncio

_STRUCT = {
    "name": "Sweet Spot",
    "sport": "cycling",
    "elements": [
        {
            "intensity": "active",
            "duration_s": 1200,
            "target": {"type": "power_pct_ftp", "low": 0.9, "high": 0.92},
        }
    ],
}


async def test_generate_day_adjustment_persists_recommendation(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)

    w = WorkoutPlanned(
        athlete_id=a.id,
        created_by=a.id,
        planned_date=date.today() + timedelta(days=1),
        name="Sweet Spot",
        structure=_STRUCT,
    )
    session.add(w)
    await session.flush()

    rec = await generate_day_adjustment(session, ctx, a.id, workout_planned=w)

    assert rec.kind == "day_adjustment"
    assert rec.target_date == w.planned_date
    assert "adjusted_structure" in rec.payload
    assert "change_summary" in rec.payload
    assert "planned_snapshot" in rec.payload
    assert "changed" in rec.payload
    assert "signals" in rec.payload
    assert rec.decision == RecommendationDecision.PENDING
    assert "workout_planned_id" in rec.payload
    assert rec.payload["workout_planned_id"] == str(w.id)
