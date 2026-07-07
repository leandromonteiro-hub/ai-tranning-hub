"""AI recommendation, evidence and feedback schemas."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RecommendationDecision, RiskLevel


class RecommendationRequest(BaseModel):
    target_date: date | None = None
    kind: str = "daily_workout"
    question: str | None = None


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    evidence_type: str
    description: str
    similarity: float | None = None


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    target_date: date | None = None
    kind: str
    summary: str
    physiological_objective: str | None = None
    block_relation: str | None = None
    rationale: str | None = None
    adjust_if_tired: str | None = None
    adjust_if_less_time: str | None = None
    payload: dict | None = None
    risk_level: RiskLevel
    risk_flags: dict | None = None
    confidence: float | None = None
    confidence_rationale: str | None = None
    decision: RecommendationDecision
    created_at: datetime
    evidence: list[EvidenceRead] = []


class DecisionRequest(BaseModel):
    decision: RecommendationDecision
    modified_payload: dict | None = None
    comment: str | None = None
    chosen_variant: Literal["ai", "methodology"] = "ai"


class FeedbackRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    made_sense: bool | None = None
    observed_result: str | None = None
    comment: str | None = None


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    recommendation_id: uuid.UUID
    athlete_id: uuid.UUID
    rating: int
    made_sense: bool | None = None
    observed_result: str | None = None
    comment: str | None = None
    created_at: datetime
