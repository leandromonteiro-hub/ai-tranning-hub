from datetime import date
from app.services.ai.feedback_context import FeedbackItem, summarize


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
