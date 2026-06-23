# backend/app/tests/test_workout/test_recommender_structured.py
from datetime import date

import pytest

from app.models.metrics import FtpHistory
from app.services.ai.recommender import generate_recommendation
from app.tests.conftest import ctx_for

pytestmark = pytest.mark.asyncio


async def test_recommendation_includes_structured_workout_when_ftp_present(
    session, two_athletes
):
    a, _ = two_athletes
    ctx = ctx_for(a)
    session.add(FtpHistory(athlete_id=a.id, created_by=a.id,
                           ftp_watts=240.0, valid_from=date(2026, 1, 1)))
    await session.flush()

    rec = await generate_recommendation(
        session, ctx, a.id, target_date=date(2026, 6, 23), kind="daily_workout"
    )
    sw = rec.payload.get("structured_workout")
    assert sw is not None
    assert sw["ftp_watts"] == 240.0
    assert len(sw["elements"]) >= 1


async def test_recommendation_has_no_structured_workout_without_ftp(
    session, two_athletes
):
    a, _ = two_athletes
    rec = await generate_recommendation(
        session, ctx_for(a), a.id, target_date=date(2026, 6, 23), kind="daily_workout"
    )
    assert (rec.payload or {}).get("structured_workout") is None
