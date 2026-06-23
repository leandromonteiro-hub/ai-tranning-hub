"""Post-execution feedback on recommendations — first-class validation data."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.models.ai import AiRecommendationFeedback
from app.repositories.ai_repo import FeedbackRepository, RecommendationRepository
from app.schemas.ai import FeedbackRead, FeedbackRequest

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/{rec_id}", response_model=FeedbackRead, status_code=201)
async def submit_feedback(
    rec_id: uuid.UUID,
    body: FeedbackRequest,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    rec_repo = RecommendationRepository(db, ctx)
    rec = await rec_repo.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    fb_repo = FeedbackRepository(db, ctx)
    feedback = AiRecommendationFeedback(
        athlete_id=ctx.athlete_id,
        recommendation_id=rec_id,
        rating=body.rating,
        made_sense=body.made_sense,
        observed_result=body.observed_result,
        comment=body.comment,
    )
    await fb_repo.add(feedback)
    return FeedbackRead.model_validate(feedback)


@router.get("/{rec_id}", response_model=list[FeedbackRead])
async def list_feedback(
    rec_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    repo = FeedbackRepository(db, ctx)
    items = [f for f in await repo.list() if f.recommendation_id == rec_id]
    return [FeedbackRead.model_validate(f) for f in items]
