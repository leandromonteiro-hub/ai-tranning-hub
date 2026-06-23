"""Collect traceable historical evidence backing a recommendation.

Each evidence item points at a real row (table + id) in the athlete's data so the
recommendation is fully auditable. Evidence is gathered from recent completed
workouts and similar past sessions.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.ai import AiRecommendationEvidence
from app.repositories.workout_repo import WorkoutRepository


@dataclass
class EvidenceItem:
    evidence_type: str
    ref_table: str
    ref_id: uuid.UUID
    description: str
    similarity: float | None = None


async def collect_evidence(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    as_of: date | None = None,
    limit: int = 5,
) -> list[EvidenceItem]:
    as_of = as_of or date.today()
    workout_repo = WorkoutRepository(session, ctx)
    recent = await workout_repo.list_between(
        as_of - timedelta(days=28), as_of, athlete_id
    )
    recent = sorted(recent, key=lambda w: w.workout_date, reverse=True)[:limit]

    items: list[EvidenceItem] = []
    for w in recent:
        desc = (
            f"{w.workout_date} {w.workout_type.value} "
            f"TSS={w.tss:.0f} " if w.tss else f"{w.workout_date} {w.workout_type.value} "
        )
        if w.normalized_power:
            desc += f"NP={w.normalized_power:.0f}W "
        if w.avg_hr:
            desc += f"avgHR={w.avg_hr:.0f} "
        items.append(
            EvidenceItem(
                evidence_type="workout",
                ref_table="workouts_completed",
                ref_id=w.id,
                description=desc.strip(),
            )
        )
    return items


def to_models(
    athlete_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    items: list[EvidenceItem],
) -> list[AiRecommendationEvidence]:
    return [
        AiRecommendationEvidence(
            athlete_id=athlete_id,
            recommendation_id=recommendation_id,
            evidence_type=it.evidence_type,
            ref_table=it.ref_table,
            ref_id=it.ref_id,
            description=it.description,
            similarity=it.similarity,
        )
        for it in items
    ]
