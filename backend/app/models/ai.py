"""AI recommendations, their evidence, decisions, feedback and LLM call logs.

These tables are the auditable spine of the Training Intelligence Layer:
every recommendation records the prompt template version, model, confidence,
risks and the *real* historical evidence it relied on — kept strictly
separate from the athlete's raw data tables.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin
from app.models.enums import RecommendationDecision, RiskLevel
from app.models.types import EnumStr, jsonb


class AiRecommendation(Base, TenantMixin):
    """A single explainable recommendation produced by the AI layer."""

    __tablename__ = "ai_recommendations"

    target_date: Mapped[date | None] = mapped_column(index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="daily_workout")  # daily/weekly/race_plan/...
    question: Mapped[str | None] = mapped_column(Text, nullable=True)  # NL question, if any

    # The recommendation payload + mandatory explainability fields
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    physiological_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    block_relation: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    adjust_if_tired: Mapped[str | None] = mapped_column(Text, nullable=True)
    adjust_if_less_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)  # structured workout

    # Safety + provenance
    risk_level: Mapped[RiskLevel] = mapped_column(EnumStr(RiskLevel, 8), default=RiskLevel.LOW)
    risk_flags: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..1
    confidence_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    prompt_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_templates.id"), nullable=True
    )
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("llm_call_logs.id"), nullable=True
    )

    decision: Mapped[RecommendationDecision] = mapped_column(
        EnumStr(RecommendationDecision, 16), default=RecommendationDecision.PENDING
    )

    evidence: Mapped[list["AiRecommendationEvidence"]] = relationship(
        back_populates="recommendation"
    )
    feedback: Mapped[list["AiRecommendationFeedback"]] = relationship(
        back_populates="recommendation"
    )


class AiRecommendationEvidence(Base, TenantMixin):
    """A traceable pointer to real historical data backing a recommendation."""

    __tablename__ = "ai_recommendation_evidence"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_recommendations.id"), index=True, nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(64))  # workout/load_metric/race/power_curve
    ref_table: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    description: Mapped[str] = mapped_column(Text)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)

    recommendation: Mapped[AiRecommendation] = relationship(back_populates="evidence")


class AiDecision(Base, TenantMixin):
    """Log of the athlete's decision (accept/reject/modify) on a recommendation."""

    __tablename__ = "ai_decisions"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_recommendations.id"), index=True, nullable=False
    )
    decision: Mapped[RecommendationDecision] = mapped_column(EnumStr(RecommendationDecision, 16))
    modified_payload: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class AiRecommendationFeedback(Base, TenantMixin):
    """Athlete feedback AFTER executing the recommendation. First-class data."""

    __tablename__ = "ai_recommendation_feedback"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_recommendations.id"), index=True, nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..5
    made_sense: Mapped[bool | None] = mapped_column(nullable=True)
    observed_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    recommendation: Mapped[AiRecommendation] = relationship(back_populates="feedback")


class LlmCallLog(Base):
    """Every LLM invocation: prompt, response, model, tokens, latency, est. cost.

    Not tenant-scoped on its own column set (it references the recommendation),
    but always created in the same transaction as the recommendation.
    """

    __tablename__ = "llm_call_logs"

    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    success: Mapped[bool] = mapped_column(default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
