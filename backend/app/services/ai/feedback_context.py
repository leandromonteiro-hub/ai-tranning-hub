"""Summarise athlete feedback for the recommendation prompt + transparency.

Mirrors profile_context.twin_seed_summary: aggregates recent feedback (rating,
made_sense, comments) into a compact PT-BR string injected as the prompt's
{feedback} section, plus a stats dict surfaced in the "Baseado em" panel. Pure
aggregation (summarize) is separated from the DB read (feedback_summary).
Feedback is grouped por tipo de treino (workout_type)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.ai import AiRecommendation, AiRecommendationFeedback

_DEFAULT_WINDOW_DAYS = 90
_DEFAULT_COMMENT_LIMIT = 5
_HALF_LIFE_DAYS = 30


@dataclass
class FeedbackItem:
    rating: int
    made_sense: bool | None
    comment: str | None
    workout_type: str | None
    when: date


def _recency_weight(when: date, as_of: date) -> float:
    """Peso exponencial por recência: 0.5^(idade_dias / meia-vida).
    Idade negativa (data futura / skew de relógio) é tratada como 0 → peso 1.0."""
    age_days = max(0, (as_of - when).days)
    return 0.5 ** (age_days / _HALF_LIFE_DAYS)


def _rate(group: list["FeedbackItem"], as_of: date) -> dict:
    n = len(group)
    weights = [_recency_weight(i.when, as_of) for i in group]
    wsum = sum(weights)
    avg = round(sum(w * i.rating for w, i in zip(weights, group)) / wsum, 1)
    answered = [(w, i.made_sense) for w, i in zip(weights, group) if i.made_sense is not None]
    if answered:
        den = sum(w for w, _ in answered)
        num = sum(w for w, m in answered if m)
        pct = round(100 * num / den)
    else:
        pct = None
    return {"count": n, "avg_rating": avg, "made_sense_pct": pct}


def summarize(items: list[FeedbackItem], comment_limit: int = _DEFAULT_COMMENT_LIMIT, *, as_of: date) -> tuple[str, dict]:
    """Aggregate feedback (most-recent-first) into (pt-BR text, stats) por tipo de treino,
    ponderado por recência (decay exponencial, meia-vida _HALF_LIFE_DAYS). ('n/d', {}) when empty."""
    if not items:
        return "n/d", {}

    overall = _rate(items, as_of)
    by_workout_type: dict[str, dict] = {}
    grouped: dict[str, list[FeedbackItem]] = {}
    for i in items:
        grouped.setdefault(i.workout_type or "—", []).append(i)
    for wtype, group in grouped.items():
        by_workout_type[wtype] = _rate(group, as_of)

    comments: list[str] = []
    for i in items:
        if i.comment and i.comment.strip():
            comments.append(f"[{i.when.isoformat()} · {i.workout_type or '—'}] {i.comment.strip()}")
        if len(comments) >= comment_limit:
            break

    stats = {**overall, "by_workout_type": by_workout_type,
             "weighted": True, "half_life_days": _HALF_LIFE_DAYS}

    head = f"Feedback recente ({overall['count']} avaliações, nota média ponderada por recência {overall['avg_rating']}"
    if overall["made_sense_pct"] is not None:
        head += f", fez sentido {overall['made_sense_pct']}%"
    head += ")"
    parts = [head]

    type_bits = []
    for wtype, s in by_workout_type.items():
        if wtype == "—":
            continue
        bit = f"{wtype} {s['avg_rating']}/5"
        if s["made_sense_pct"] is not None:
            bit += f" ({s['made_sense_pct']}% fez sentido)"
        type_bits.append(bit)
    if type_bits:
        parts.append("Por tipo: " + ", ".join(type_bits))
    if comments:
        parts.append("Comentários: " + "; ".join(comments))

    return " · ".join(parts), stats


async def feedback_summary(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    comment_limit: int = _DEFAULT_COMMENT_LIMIT,
) -> tuple[str, dict]:
    """Read recent feedback for one athlete (tenant-scoped) and summarise it."""
    ctx.assert_can_access(athlete_id)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    stmt = (
        select(AiRecommendationFeedback, AiRecommendation)
        .join(AiRecommendation,
              AiRecommendationFeedback.recommendation_id == AiRecommendation.id)
        .where(
            AiRecommendationFeedback.athlete_id == athlete_id,
            AiRecommendationFeedback.deleted_at.is_(None),
            AiRecommendationFeedback.created_at >= cutoff,
        )
        .order_by(AiRecommendationFeedback.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    items: list[FeedbackItem] = []
    for fb, rec in rows:
        workout_type = ((rec.payload or {}).get("signals") or {}).get("workout_type")
        when = (fb.created_at or now).date()
        items.append(FeedbackItem(
            rating=fb.rating, made_sense=fb.made_sense,
            comment=fb.comment, workout_type=workout_type, when=when,
        ))
    return summarize(items, comment_limit, as_of=now.date())
