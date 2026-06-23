"""Repository for AI recommendations, decisions and feedback."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.ai import (
    AiDecision,
    AiRecommendation,
    AiRecommendationFeedback,
)
from app.repositories.base import TenantRepository


class RecommendationRepository(TenantRepository[AiRecommendation]):
    model = AiRecommendation

    async def get_with_evidence(
        self, rec_id: uuid.UUID, athlete_id: uuid.UUID | None = None
    ) -> AiRecommendation | None:
        # Evidence is loaded lazily via relationship; get() applies tenant scope.
        return await self.get(rec_id, athlete_id)


class FeedbackRepository(TenantRepository[AiRecommendationFeedback]):
    model = AiRecommendationFeedback

    async def list_all_for_admin(self) -> list[AiRecommendationFeedback]:
        """Admin-only: every feedback across tenants. Caller MUST be admin."""
        if not self.ctx.is_admin:
            from app.core.tenant import TenantViolationError

            raise TenantViolationError("Admin role required for cross-tenant feedback")
        stmt = select(AiRecommendationFeedback).where(
            AiRecommendationFeedback.deleted_at.is_(None)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())


class DecisionRepository(TenantRepository[AiDecision]):
    model = AiDecision
