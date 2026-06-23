"""Admin-only routes (prefix /admin, role-gated): athletes, feedback, usage."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.ai import AiRecommendation, AiRecommendationFeedback
from app.models.athlete import Athlete
from app.models.workout import WorkoutCompleted
from app.repositories.athlete_repo import AthleteRepository
from app.schemas.ai import FeedbackRead
from app.schemas.athlete import AthleteRead
from app.schemas.auth import CurrentUser
from app.services.ai import rag
from app.services.knowledge.embedder import embed_text
from app.services.knowledge.knowledge_service import (
    ingest_curated_knowledge,
    knowledge_stats,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/athletes", response_model=list[AthleteRead])
async def list_athletes(db: AsyncSession = Depends(get_db)):
    athletes = await AthleteRepository(db).list_all()
    return [AthleteRead.model_validate(a) for a in athletes]


@router.get("/feedback", response_model=list[FeedbackRead])
async def all_feedback(db: AsyncSession = Depends(get_db)):
    """Every feedback across all tenants — the admin validation dashboard feed."""
    stmt = select(AiRecommendationFeedback).where(
        AiRecommendationFeedback.deleted_at.is_(None)
    ).order_by(AiRecommendationFeedback.created_at.desc())
    res = await db.execute(stmt)
    return [FeedbackRead.model_validate(f) for f in res.scalars().all()]


@router.get("/usage")
async def usage_metrics(db: AsyncSession = Depends(get_db)):
    """Aggregate usage + recommendation-quality metrics for the validation phase."""
    async def _count(model) -> int:
        res = await db.execute(
            select(func.count()).select_from(model).where(model.deleted_at.is_(None))
        )
        return int(res.scalar() or 0)

    avg_rating_res = await db.execute(
        select(func.avg(AiRecommendationFeedback.rating)).where(
            AiRecommendationFeedback.deleted_at.is_(None)
        )
    )
    return {
        "athletes": await _count(Athlete),
        "workouts": await _count(WorkoutCompleted),
        "recommendations": await _count(AiRecommendation),
        "feedback_count": await _count(AiRecommendationFeedback),
        "avg_feedback_rating": float(avg_rating_res.scalar() or 0.0),
    }


@router.post("/knowledge/seed")
async def seed_knowledge(db: AsyncSession = Depends(get_db)):
    """Populate the global training-knowledge base (idempotent)."""
    result = await ingest_curated_knowledge(db)
    stats = await knowledge_stats(db)
    return {**result, **stats}


@router.get("/knowledge/stats")
async def get_knowledge_stats(db: AsyncSession = Depends(get_db)):
    return await knowledge_stats(db)


@router.get("/knowledge/search")
async def search_knowledge(
    q: str = Query(..., min_length=2),
    k: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Semantic search over the global knowledge base (RAG retrieval check)."""
    vec = embed_text(q)
    hits = await rag.search_knowledge(db, vec, k=k)
    return [{"chunk": h.chunk_text, "ref_id": str(h.ref_id)} for h in hits]
