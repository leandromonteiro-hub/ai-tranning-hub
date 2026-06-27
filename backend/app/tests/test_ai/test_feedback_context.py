import uuid
import pytest
from datetime import date

from app.core.tenant import TenantContext
from app.models.ai import AiRecommendation, AiRecommendationFeedback
from app.models.enums import RecommendationDecision, RiskLevel
from app.services.ai.feedback_context import FeedbackItem, summarize, feedback_summary


def _ctx(aid):
    from app.models.enums import Role
    return TenantContext(athlete_id=aid, tenant_id="t", role=Role.ATHLETE)


async def _seed_feedback(session, aid, *, rating, made_sense, comment, block):
    rec = AiRecommendation(
        athlete_id=aid, target_date=date(2026, 6, 20), kind="daily_workout",
        summary="s", risk_level=RiskLevel.LOW, decision=RecommendationDecision.PENDING,
        payload={"signals": {"block": block}},
    )
    session.add(rec)
    await session.flush()
    session.add(AiRecommendationFeedback(
        athlete_id=aid, recommendation_id=rec.id, rating=rating,
        made_sense=made_sense, comment=comment,
    ))
    await session.flush()


def _items():
    # mais recente primeiro
    return [
        FeedbackItem(5, True, "perfeito", "BASE", date(2026, 6, 20)),
        FeedbackItem(3, False, "muito puxado no fim", "BUILD", date(2026, 6, 12)),
        FeedbackItem(4, True, None, "BUILD", date(2026, 6, 5)),
    ]


def test_summarize_aggregates_overall_and_by_block():
    text, stats = summarize(_items())
    assert stats["count"] == 3
    assert stats["avg_rating"] == 4.0
    assert stats["made_sense_pct"] == 67  # 2 de 3 made_sense responderam, 2 True -> 67%
    assert stats["by_block"]["BUILD"]["count"] == 2
    assert stats["by_block"]["BUILD"]["avg_rating"] == 3.5
    assert "Feedback recente (3 avaliações, nota média 4.0" in text
    assert "Por bloco:" in text


def test_summarize_includes_recent_comments_with_label():
    text, _ = summarize(_items(), comment_limit=5)
    assert "[2026-06-20 · BASE] perfeito" in text
    assert "[2026-06-12 · BUILD] muito puxado no fim" in text


def test_summarize_respects_comment_limit_most_recent_first():
    text, _ = summarize(_items(), comment_limit=1)
    assert "perfeito" in text          # mais recente
    assert "muito puxado" not in text  # cortado pelo limite


def test_summarize_empty_is_nd():
    assert summarize([]) == ("n/d", {})


def test_summarize_block_none_groups_under_dash():
    text, stats = summarize([FeedbackItem(4, None, None, None, date(2026, 6, 1))])
    assert stats["by_block"]["—"]["count"] == 1
    assert stats["made_sense_pct"] is None   # ninguém respondeu made_sense
    assert "Por bloco:" not in text          # "—" não vira recorte textual


@pytest.mark.asyncio
async def test_feedback_summary_reads_and_aggregates(session):
    aid = uuid.uuid4()
    await _seed_feedback(session, aid, rating=5, made_sense=True, comment="bom", block="BASE")
    await _seed_feedback(session, aid, rating=3, made_sense=False, comment="puxado", block="BUILD")
    text, stats = await feedback_summary(session, _ctx(aid), aid)
    assert stats["count"] == 2
    assert "Feedback recente (2 avaliações" in text
    assert "bom" in text or "puxado" in text


@pytest.mark.asyncio
async def test_feedback_summary_empty_is_nd(session):
    aid = uuid.uuid4()
    assert await feedback_summary(session, _ctx(aid), aid) == ("n/d", {})


@pytest.mark.asyncio
async def test_feedback_summary_isolated_per_athlete(session):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed_feedback(session, a, rating=5, made_sense=True, comment="de A", block="BASE")
    text_b, stats_b = await feedback_summary(session, _ctx(b), b)
    assert (text_b, stats_b) == ("n/d", {})  # B não vê o feedback de A
