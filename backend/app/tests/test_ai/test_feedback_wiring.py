import uuid
import pytest
from datetime import date, timedelta

from app.models.ai import AiRecommendation, AiRecommendationFeedback
from app.models.enums import RecommendationDecision, RiskLevel
from app.models.metrics import FtpHistory
from app.models.workout import WorkoutPlanned
from app.services.ai.recommender import generate_day_adjustment, generate_recommendation
from app.tests.conftest import ctx_for

pytestmark = pytest.mark.asyncio


async def test_recommendation_payload_carries_feedback_stats(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    session.add(FtpHistory(athlete_id=a.id, created_by=a.id, ftp_watts=240.0,
                           valid_from=date(2026, 1, 1)))
    prior = AiRecommendation(
        athlete_id=a.id, target_date=date(2026, 6, 1), kind="daily_workout",
        summary="s", risk_level=RiskLevel.LOW, decision=RecommendationDecision.PENDING,
        payload={"signals": {"block": "BASE"}},
    )
    session.add(prior)
    await session.flush()
    session.add(AiRecommendationFeedback(athlete_id=a.id, recommendation_id=prior.id,
                                         rating=5, made_sense=True, comment="ótimo"))
    await session.flush()

    rec = await generate_recommendation(session, ctx, a.id,
                                        target_date=date(2026, 6, 23), kind="daily_workout")
    fb = (rec.payload or {}).get("signals", {}).get("feedback")
    assert fb is not None
    assert fb["count"] >= 1


async def test_day_adjustment_payload_carries_feedback_stats(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    prior = AiRecommendation(
        athlete_id=a.id, target_date=date(2026, 6, 1), kind="daily_workout",
        summary="s", risk_level=RiskLevel.LOW, decision=RecommendationDecision.PENDING,
        payload={"signals": {"block": "BASE"}},
    )
    session.add(prior)
    await session.flush()
    session.add(AiRecommendationFeedback(athlete_id=a.id, recommendation_id=prior.id,
                                         rating=4, made_sense=True, comment="bom"))
    w = WorkoutPlanned(
        athlete_id=a.id, created_by=a.id,
        planned_date=date.today() + timedelta(days=1), name="Sweet Spot",
        structure={"name": "Sweet Spot", "sport": "cycling", "elements": [
            {"intensity": "active", "duration_s": 1200,
             "target": {"type": "power_pct_ftp", "low": 0.9, "high": 0.92}}]},
    )
    session.add(w)
    await session.flush()

    rec = await generate_day_adjustment(session, ctx, a.id, workout_planned=w)
    fb = (rec.payload or {}).get("signals", {}).get("feedback")
    assert fb is not None
    assert fb["count"] >= 1
