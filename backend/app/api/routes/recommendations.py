"""Recommendation generation, retrieval and athlete decision logging."""
from __future__ import annotations

import unicodedata
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.models.ai import AiDecision
from app.repositories.ai_repo import DecisionRepository, RecommendationRepository
from app.schemas.ai import DecisionRequest, RecommendationRead, RecommendationRequest
from app.services.ai.recommender import generate_recommendation
from app.services.workout.fit_encoder import encode as encode_fit
from app.services.workout.model import StructuredWorkout

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("", response_model=RecommendationRead, status_code=201)
async def create_recommendation(
    body: RecommendationRequest,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    rec = await generate_recommendation(
        db, ctx, ctx.athlete_id,
        target_date=body.target_date, kind=body.kind, question=body.question,
    )
    await db.refresh(rec, attribute_names=["evidence"])
    return RecommendationRead.model_validate(rec)


@router.get("", response_model=list[RecommendationRead])
async def list_recommendations(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    repo = RecommendationRepository(db, ctx)
    recs = await repo.list()
    out = []
    for r in recs:
        await db.refresh(r, attribute_names=["evidence"])
        out.append(RecommendationRead.model_validate(r))
    return out


@router.get("/{rec_id}", response_model=RecommendationRead)
async def get_recommendation(
    rec_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    repo = RecommendationRepository(db, ctx)
    rec = await repo.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    await db.refresh(rec, attribute_names=["evidence"])
    return RecommendationRead.model_validate(rec)


@router.get("/{rec_id}/export.fit")
async def export_recommendation_fit(
    rec_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Download the recommendation's structured workout as a Garmin FIT file."""
    repo = RecommendationRepository(db, ctx)
    rec = await repo.get(rec_id)
    sw_data = (rec.payload or {}).get("structured_workout") if rec else None
    if not sw_data:
        raise HTTPException(status_code=404, detail="No structured workout for this recommendation")
    workout = StructuredWorkout.model_validate(sw_data)
    data = encode_fit(workout)
    ascii_name = unicodedata.normalize("NFKD", workout.name).encode("ascii", "ignore").decode("ascii")
    slug = "".join(c if c.isalnum() else "_" for c in ascii_name).strip("_") or "workout"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{slug}.fit"'},
    )


@router.post("/{rec_id}/decision", response_model=RecommendationRead)
async def record_decision(
    rec_id: uuid.UUID,
    body: DecisionRequest,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Athlete accepts / rejects / modifies a recommendation (logged + auditable)."""
    repo = RecommendationRepository(db, ctx)
    rec = await repo.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    rec.decision = body.decision
    db.add(rec)
    decision_repo = DecisionRepository(db, ctx)
    await decision_repo.add(
        AiDecision(
            athlete_id=ctx.athlete_id,
            recommendation_id=rec.id,
            decision=body.decision,
            modified_payload=body.modified_payload,
            comment=body.comment,
        )
    )
    await db.refresh(rec, attribute_names=["evidence"])
    return RecommendationRead.model_validate(rec)
