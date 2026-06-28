import uuid
import pytest
from datetime import date

from app.core.tenant import TenantContext
from app.models.ai import AiRecommendation, AiRecommendationFeedback
from app.models.enums import RecommendationDecision, RiskLevel
from app.services.ai.feedback_context import FeedbackItem, summarize, feedback_summary, _recency_weight


def _ctx(aid):
    from app.models.enums import Role
    return TenantContext(athlete_id=aid, tenant_id="t", role=Role.ATHLETE)


async def _seed_feedback(session, aid, *, rating, made_sense, comment, workout_type):
    rec = AiRecommendation(
        athlete_id=aid, target_date=date(2026, 6, 20), kind="daily_workout",
        summary="s", risk_level=RiskLevel.LOW, decision=RecommendationDecision.PENDING,
        payload={"signals": {"workout_type": workout_type}},
    )
    session.add(rec)
    await session.flush()
    session.add(AiRecommendationFeedback(
        athlete_id=aid, recommendation_id=rec.id, rating=rating,
        made_sense=made_sense, comment=comment,
    ))
    await session.flush()


_AS_OF = date(2026, 6, 20)


def _items():
    # mais recente primeiro (datas relativas a _AS_OF)
    return [
        FeedbackItem(5, True, "perfeito", "ENDURANCE", date(2026, 6, 20)),
        FeedbackItem(3, False, "muito puxado no fim", "VO2MAX", date(2026, 6, 12)),
        FeedbackItem(4, True, None, "VO2MAX", date(2026, 6, 5)),
    ]


def test_summarize_aggregates_overall_and_by_workout_type():
    text, stats = summarize(_items(), as_of=_AS_OF)
    assert stats["count"] == 3
    # média PONDERADA por recência (o 5 de hoje puxa acima da média simples 4.0)
    assert stats["avg_rating"] == 4.1
    assert stats["weighted"] is True
    assert stats["half_life_days"] == 30
    assert stats["made_sense_pct"] == 67  # True(w1.0)+True(w.71) sobre True+False+True ponderado
    assert stats["by_workout_type"]["VO2MAX"]["count"] == 2
    assert stats["by_workout_type"]["VO2MAX"]["avg_rating"] == 3.5
    assert "Feedback recente (3 avaliações, nota média ponderada por recência 4.1" in text
    assert "Por tipo:" in text


def test_summarize_includes_recent_comments_with_label():
    text, _ = summarize(_items(), comment_limit=5, as_of=_AS_OF)
    assert "[2026-06-20 · ENDURANCE] perfeito" in text
    assert "[2026-06-12 · VO2MAX] muito puxado no fim" in text


def test_summarize_respects_comment_limit_most_recent_first():
    text, _ = summarize(_items(), comment_limit=1, as_of=_AS_OF)
    assert "perfeito" in text          # mais recente
    assert "muito puxado" not in text  # cortado pelo limite


def test_summarize_empty_is_nd():
    assert summarize([], as_of=_AS_OF) == ("n/d", {})


def test_summarize_type_none_groups_under_dash():
    text, stats = summarize([FeedbackItem(4, None, None, None, date(2026, 6, 1))], as_of=_AS_OF)
    assert stats["by_workout_type"]["—"]["count"] == 1
    assert stats["made_sense_pct"] is None   # ninguém respondeu made_sense
    assert "Por tipo:" not in text           # "—" não vira recorte textual


def test_summarize_weights_recent_feedback_more():
    as_of = date(2026, 6, 30)
    items = [
        FeedbackItem(5, True, None, "ENDURANCE", date(2026, 6, 30)),   # hoje, w=1.0
        FeedbackItem(1, True, None, "ENDURANCE", date(2026, 4, 1)),    # 90d atrás, w≈0.125
    ]
    _, stats = summarize(items, as_of=as_of)
    # média simples seria 3.0; ponderada favorece fortemente o 5 recente
    assert stats["avg_rating"] > 4.0


def test_summarize_same_age_equals_simple_mean():
    as_of = date(2026, 6, 30)
    items = [
        FeedbackItem(2, None, None, "ENDURANCE", date(2026, 6, 20)),
        FeedbackItem(4, None, None, "ENDURANCE", date(2026, 6, 20)),
    ]
    _, stats = summarize(items, as_of=as_of)
    assert stats["avg_rating"] == 3.0  # mesma idade → pesos se cancelam


@pytest.mark.asyncio
async def test_feedback_summary_reads_and_aggregates(session):
    aid = uuid.uuid4()
    await _seed_feedback(session, aid, rating=5, made_sense=True, comment="bom", workout_type="ENDURANCE")
    await _seed_feedback(session, aid, rating=3, made_sense=False, comment="puxado", workout_type="VO2MAX")
    text, stats = await feedback_summary(session, _ctx(aid), aid)
    assert stats["count"] == 2
    assert stats["weighted"] is True       # prova que as_of foi injetado e a média é ponderada
    assert stats["half_life_days"] == 30
    assert stats["by_workout_type"]["VO2MAX"]["count"] == 1
    assert "Feedback recente (2 avaliações" in text
    assert "bom" in text or "puxado" in text


@pytest.mark.asyncio
async def test_feedback_summary_empty_is_nd(session):
    aid = uuid.uuid4()
    assert await feedback_summary(session, _ctx(aid), aid) == ("n/d", {})


@pytest.mark.asyncio
async def test_feedback_summary_isolated_per_athlete(session):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed_feedback(session, a, rating=5, made_sense=True, comment="de A", workout_type="ENDURANCE")
    text_b, stats_b = await feedback_summary(session, _ctx(b), b)
    assert (text_b, stats_b) == ("n/d", {})  # B não vê o feedback de A


def test_recency_weight_today_is_one():
    assert _recency_weight(date(2026, 6, 30), date(2026, 6, 30)) == 1.0


def test_recency_weight_one_halflife_is_half():
    # 30 dias = uma meia-vida
    assert _recency_weight(date(2026, 5, 31), date(2026, 6, 30)) == pytest.approx(0.5)


def test_recency_weight_two_halflives_is_quarter():
    # 60 dias = duas meias-vidas
    assert _recency_weight(date(2026, 5, 1), date(2026, 6, 30)) == pytest.approx(0.25)


def test_recency_weight_future_date_clamps_to_one():
    # data futura (skew) → idade 0 → peso 1.0
    assert _recency_weight(date(2026, 7, 5), date(2026, 6, 30)) == 1.0
