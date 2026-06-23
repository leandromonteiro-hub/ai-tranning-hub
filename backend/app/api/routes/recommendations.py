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
from app.models.enums import BlockType, RiskLevel
from app.repositories.ai_repo import DecisionRepository, RecommendationRepository
from app.schemas.ai import DecisionRequest, RecommendationRead, RecommendationRequest
from app.services.ai.profile_context import anamnese_complete, fetch_profile
from app.services.ai.recommender import generate_recommendation
from app.services.workout.builder import build_for
from app.services.workout.fit_encoder import encode as encode_fit
from app.services.workout.model import StructuredWorkout
from app.services.workout.zwo_encoder import encode_zwo

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

# Named sample workouts for device-import testing (template -> block, risk).
_SAMPLE_TEMPLATES: dict[str, tuple[BlockType, RiskLevel]] = {
    "sweet_spot": (BlockType.BUILD, RiskLevel.LOW),
    "vo2max": (BlockType.PEAK, RiskLevel.LOW),
    "endurance": (BlockType.BASE, RiskLevel.LOW),
    "recovery": (BlockType.BASE, RiskLevel.HIGH),  # HIGH forces the recovery template
}


def _slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return "".join(c if c.isalnum() else "_" for c in ascii_name).strip("_") or "workout"


def _download(content, slug: str, ext: str) -> Response:
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{slug}.{ext}"'},
    )


def _fit_response(workout: StructuredWorkout) -> Response:
    """Encode a structured workout to a downloadable .fit attachment (device-native)."""
    return _download(encode_fit(workout), _slug(workout.name), "fit")


def _zwo_response(workout: StructuredWorkout) -> Response:
    """Encode a structured workout to a downloadable .zwo attachment (TrainingPeaks import)."""
    return _download(encode_zwo(workout), _slug(workout.name), "zwo")


@router.post("", response_model=RecommendationRead, status_code=201)
async def create_recommendation(
    body: RecommendationRequest,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    profile = await fetch_profile(db, ctx.athlete_id)
    if not anamnese_complete(profile):
        raise HTTPException(
            status_code=409,
            detail="Anamnese incompleta — complete seu perfil antes de gerar recomendações.",
        )
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


@router.get("/sample.fit")
async def sample_workout_fit(
    template: str = "sweet_spot",
    ftp: float = 250.0,
    ctx: TenantContext = Depends(get_tenant),
):
    """Download a sample structured workout as a Garmin FIT file (for device-import testing).

    ``template`` is one of: sweet_spot, vo2max, endurance, recovery. ``ftp`` (watts)
    scales the power targets. Requires authentication but reads no athlete data.
    """
    if template not in _SAMPLE_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown template; choose one of {sorted(_SAMPLE_TEMPLATES)}",
        )
    if ftp <= 0:
        raise HTTPException(status_code=400, detail="ftp must be positive")
    block, risk = _SAMPLE_TEMPLATES[template]
    return _fit_response(build_for(block, risk, ftp))


@router.get("/sample.zwo")
async def sample_workout_zwo(
    template: str = "sweet_spot",
    ftp: float = 250.0,
    ctx: TenantContext = Depends(get_tenant),
):
    """Download a sample structured workout as a Zwift .zwo file (TrainingPeaks import).

    ``template`` is one of: sweet_spot, vo2max, endurance, recovery. Power is %FTP,
    so ``ftp`` does not change the .zwo (the importing platform applies the athlete FTP).
    """
    if template not in _SAMPLE_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown template; choose one of {sorted(_SAMPLE_TEMPLATES)}",
        )
    if ftp <= 0:
        raise HTTPException(status_code=400, detail="ftp must be positive")
    block, risk = _SAMPLE_TEMPLATES[template]
    return _zwo_response(build_for(block, risk, ftp))


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
    return _fit_response(workout)


@router.get("/{rec_id}/export.zwo")
async def export_recommendation_zwo(
    rec_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Download the recommendation's structured workout as a Zwift .zwo (TrainingPeaks import)."""
    repo = RecommendationRepository(db, ctx)
    rec = await repo.get(rec_id)
    sw_data = (rec.payload or {}).get("structured_workout") if rec else None
    if not sw_data:
        raise HTTPException(status_code=404, detail="No structured workout for this recommendation")
    return _zwo_response(StructuredWorkout.model_validate(sw_data))


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
