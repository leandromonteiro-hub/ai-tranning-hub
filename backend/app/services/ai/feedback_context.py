"""Summarise athlete feedback for the recommendation prompt + transparency.

Mirrors profile_context.twin_seed_summary: aggregates recent feedback (rating,
made_sense, comments) into a compact PT-BR string injected as the prompt's
{feedback} section, plus a stats dict surfaced in the "Baseado em" panel. Pure
aggregation (summarize) is separated from the DB read (feedback_summary)."""
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


@dataclass
class FeedbackItem:
    rating: int
    made_sense: bool | None
    comment: str | None
    block: str | None
    when: date


def _rate(group: list["FeedbackItem"]) -> dict:
    n = len(group)
    avg = round(sum(i.rating for i in group) / n, 1)
    answered = [i.made_sense for i in group if i.made_sense is not None]
    pct = round(100 * sum(1 for m in answered if m) / len(answered)) if answered else None
    return {"count": n, "avg_rating": avg, "made_sense_pct": pct}


def summarize(items: list[FeedbackItem], comment_limit: int = _DEFAULT_COMMENT_LIMIT) -> tuple[str, dict]:
    """Aggregate feedback (most-recent-first) into (pt-BR text, stats). ('n/d', {}) when empty."""
    if not items:
        return "n/d", {}

    overall = _rate(items)
    by_block: dict[str, dict] = {}
    grouped: dict[str, list[FeedbackItem]] = {}
    for i in items:
        grouped.setdefault(i.block or "—", []).append(i)
    for block, group in grouped.items():
        by_block[block] = _rate(group)

    comments: list[str] = []
    for i in items:
        if i.comment and i.comment.strip():
            comments.append(f"[{i.when.isoformat()} · {i.block or '—'}] {i.comment.strip()}")
        if len(comments) >= comment_limit:
            break

    stats = {**overall, "by_block": by_block}

    head = f"Feedback recente ({overall['count']} avaliações, nota média {overall['avg_rating']}"
    if overall["made_sense_pct"] is not None:
        head += f", fez sentido {overall['made_sense_pct']}%"
    head += ")"
    parts = [head]

    block_bits = []
    for block, s in by_block.items():
        if block == "—":
            continue
        bit = f"{block} {s['avg_rating']}/5"
        if s["made_sense_pct"] is not None:
            bit += f" ({s['made_sense_pct']}% fez sentido)"
        block_bits.append(bit)
    if block_bits:
        parts.append("Por bloco: " + ", ".join(block_bits))
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
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
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
        block = ((rec.payload or {}).get("signals") or {}).get("block")
        when = (fb.created_at or datetime.now(timezone.utc)).date()
        items.append(FeedbackItem(
            rating=fb.rating, made_sense=fb.made_sense,
            comment=fb.comment, block=block, when=when,
        ))
    return summarize(items, comment_limit)
