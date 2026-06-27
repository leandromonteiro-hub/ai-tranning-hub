"""Recommendation orchestration.

Strict order of operations (enforced, not optional):
  1. Build the digital twin (real data only).
  2. Run safety guardrails. If risk is HIGH, the original ask is blocked and a
     conservative alternative is produced — the LLM is told it MUST stay
     conservative.
  3. Gather traceable historical evidence + RAG knowledge context.
  4. Render the versioned prompt template, call the logged LLM client.
  5. Persist: LlmCallLog, AiRecommendation (with risk + confidence + provenance),
     and AiRecommendationEvidence rows.

The LLM is never called before guardrails have run.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.models.ai import AiRecommendation, LlmCallLog
from app.models.enums import BlockType, RecommendationDecision, RiskLevel
from app.repositories.ai_repo import RecommendationRepository
from app.repositories.metrics_repo import FtpRepository
from app.repositories.plan_repo import TrainingWeekRepository
from app.services.ai import evidence_builder, feedback_context, profile_context, prompt_store, prompts, rag
from app.services.ai.digital_twin import build_twin
from app.services.ai.llm_client import LlmClient
from app.services.ai.safety_validator import evaluate_safety
from app.services.knowledge.embedder import embed_text
from app.services.workout import analysis as workout_analysis
from app.services.workout.builder import build_for
from app.services.workout.model import StructuredWorkout
from app.services.planning import workout_adjuster

log = get_logger(__name__)


async def generate_recommendation(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    *,
    target_date: date | None = None,
    kind: str = "daily_workout",
    question: str | None = None,
) -> AiRecommendation:
    ctx.assert_can_access(athlete_id)
    target_date = target_date or date.today()

    profile = await profile_context.fetch_profile(session, athlete_id)

    # 1. Digital twin (real data only)
    twin = await build_twin(session, ctx, athlete_id, as_of=target_date)

    # 2. Guardrails BEFORE any LLM call
    safety = evaluate_safety(twin.snapshot)
    log.info("guardrails_evaluated", extra=safety.as_dict())

    # Current periodization block (drives both the workout and the signals panel).
    block = (
        await TrainingWeekRepository(session, ctx).block_on(target_date, athlete_id)
        or BlockType.BASE
    )

    # Structured workout (deterministic, inherits the guardrail risk posture).
    ftp_watts = await FtpRepository(session, ctx).value_on(target_date, athlete_id)
    structured_workout = None
    workout_description = None
    if ftp_watts:
        workout = build_for(block, safety.risk_level, ftp_watts)
        structured_workout = workout.model_dump(mode="json")
        # Deterministic breakdown (total time, rest times, IF, TSS) for the athlete.
        workout_description = workout_analysis.describe(workout)

    # 3. Evidence + knowledge context
    evidence_items = await evidence_builder.collect_evidence(
        session, ctx, athlete_id, as_of=target_date
    )
    evidence_text = "\n".join(f"- {e.description}" for e in evidence_items) or "n/d"

    query = question or f"Recommend a {kind} for {target_date}."
    # RAG over the knowledge base is best-effort: if pgvector / the embeddings
    # table is unavailable (e.g. empty KB or SQLite tests), degrade gracefully
    # rather than failing the whole recommendation.
    try:
        qvec = embed_text(query)
        knowledge_chunks = await rag.search_knowledge(session, qvec, k=3)
        knowledge_text = "\n".join(f"- {c.chunk_text[:300]}" for c in knowledge_chunks) or "n/d"
    except Exception:  # noqa: BLE001
        log.warning("knowledge_retrieval_skipped")
        knowledge_text = "n/d"

    safety_text = (
        f"risk_level={safety.risk_level.value}, block_original={safety.block_original}, "
        f"flags={[f['indicator'] + ':' + f['severity'] for f in safety.flags]}"
    )

    # 4. Render versioned template + logged LLM call
    methodology = profile_context.twin_seed_summary(profile)
    feedback_text, feedback_stats = await feedback_context.feedback_summary(
        session, ctx, athlete_id
    )
    template_version, template_body = prompts.ACTIVE_TEMPLATES[kind] if kind in prompts.ACTIVE_TEMPLATES else (1, prompts.DAILY_WORKOUT_TEMPLATE)
    prompt = prompts.render_daily_workout(
        twin=twin.summary,
        safety=safety_text,
        evidence=evidence_text,
        knowledge=knowledge_text,
        profile=profile_context.profile_summary(profile),
        methodology=methodology,
        feedback=feedback_text,
        question=query if not safety.block_original else (
            query + "\n\nNOTE: guardrails flagged HIGH risk — you MUST recommend a "
            "conservative recovery-oriented alternative only."
        ),
    )
    client = LlmClient()
    llm = client.complete(prompt, system=prompts.SYSTEM_PROMPT)

    call_log = LlmCallLog(
        provider=llm.provider, model=llm.model, prompt=prompt, response=llm.text,
        prompt_tokens=llm.prompt_tokens, completion_tokens=llm.completion_tokens,
        latency_ms=llm.latency_ms, estimated_cost_usd=llm.estimated_cost_usd,
        success=llm.success, error_message=llm.error_message,
    )
    session.add(call_log)
    await session.flush()

    # 5. Persist recommendation with full provenance
    template_id = await prompt_store.active_template_id(session, kind if kind in prompts.ACTIVE_TEMPLATES else "daily_workout")
    confidence, conf_rationale = _confidence(safety.risk_level, bool(evidence_items))
    signals = _signals(twin.snapshot, methodology, block, ftp_watts)
    signals["feedback"] = feedback_stats
    rec = AiRecommendation(
        athlete_id=athlete_id,
        target_date=target_date,
        kind=kind,
        question=question,
        summary=_summary(llm.text, safety),
        physiological_objective=_objective(safety),
        block_relation=f"Alinhado ao bloco atual ({block.value}) e ao estado de forma (CTL/ATL/TSB).",
        rationale=llm.text if llm.success else "LLM unavailable; conservative default applied.",
        adjust_if_tired="If more fatigued than the snapshot indicates, drop to Z1-Z2 "
        "endurance or take full rest; never push intensity on a high-fatigue day.",
        adjust_if_less_time="If less time is available, keep the primary intensity "
        "interval(s) and trim warm-up/cool-down and endurance volume.",
        payload={
            "llm_text": llm.text,
            "template_version": template_version,
            "structured_workout": structured_workout,
            "workout_description": workout_description,
            "signals": signals,
        },
        risk_level=safety.risk_level,
        risk_flags=safety.as_dict(),
        confidence=confidence,
        confidence_rationale=conf_rationale,
        prompt_template_id=template_id,
        llm_call_id=call_log.id,
        decision=RecommendationDecision.PENDING,
    )
    rec_repo = RecommendationRepository(session, ctx)
    await rec_repo.add(rec)

    for ev in evidence_builder.to_models(athlete_id, rec.id, evidence_items):
        session.add(ev)
    await session.flush()

    return rec


async def generate_day_adjustment(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    *,
    workout_planned,
) -> AiRecommendation:
    """Adjust a single planned workout to current form (deterministic), with an
    LLM-written justification. Seeded by the planned workout, not build_for."""
    ctx.assert_can_access(athlete_id)
    target_date = workout_planned.planned_date

    profile = await profile_context.fetch_profile(session, athlete_id)
    twin = await build_twin(session, ctx, athlete_id, as_of=target_date)
    safety = evaluate_safety(twin.snapshot)

    block = (
        await TrainingWeekRepository(session, ctx).block_on(target_date, athlete_id)
        or BlockType.BASE
    )
    ftp_watts = await FtpRepository(session, ctx).value_on(target_date, athlete_id)

    result = workout_adjuster.adjust(workout_planned.structure, safety.risk_level)
    adjusted_struct = result.adjusted_structure
    adjusted_tss = None
    adjusted_duration_s = None
    if adjusted_struct.get("elements"):
        sw = StructuredWorkout.model_validate(adjusted_struct)
        adjusted_duration_s = workout_analysis.total_duration_s(sw)
        adjusted_tss = workout_analysis.estimated_tss(sw)

    methodology = profile_context.twin_seed_summary(profile)
    evidence_items = await evidence_builder.collect_evidence(
        session, ctx, athlete_id, as_of=target_date
    )
    evidence_text = "\n".join(f"- {e.description}" for e in evidence_items) or "n/d"
    feedback_text, feedback_stats = await feedback_context.feedback_summary(
        session, ctx, athlete_id
    )

    question = (
        f"O treino planejado para {target_date} é '{workout_planned.name}'. "
        f"Estado de forma → risco {safety.risk_level.value}. "
        f"Resumo do ajuste determinístico: {result.change_summary}. "
        "Explique, em PT-BR e sem prometer resultados, por que esse ajuste faz "
        "sentido (ou por que manter o planejado, se não houve mudança), conectando "
        "à forma atual e à metodologia do atleta."
    )
    prompt = prompts.render_daily_workout(
        twin=twin.summary,
        safety=f"risk_level={safety.risk_level.value}",
        evidence=evidence_text,
        knowledge="n/d",
        profile=profile_context.profile_summary(profile),
        methodology=methodology,
        feedback=feedback_text,
        question=question,
    )
    client = LlmClient()
    llm = client.complete(prompt, system=prompts.SYSTEM_PROMPT)
    call_log = LlmCallLog(
        provider=llm.provider, model=llm.model, prompt=prompt, response=llm.text,
        prompt_tokens=llm.prompt_tokens, completion_tokens=llm.completion_tokens,
        latency_ms=llm.latency_ms, estimated_cost_usd=llm.estimated_cost_usd,
        success=llm.success, error_message=llm.error_message,
    )
    session.add(call_log)
    await session.flush()

    template_id = await prompt_store.active_template_id(session, "daily_workout")
    confidence, conf_rationale = _confidence(safety.risk_level, bool(evidence_items))
    signals = _signals(twin.snapshot, methodology, block, ftp_watts)
    signals["feedback"] = feedback_stats
    rec = AiRecommendation(
        athlete_id=athlete_id, target_date=target_date, kind="day_adjustment",
        question=question, summary=_summary(llm.text, safety),
        physiological_objective=_objective(safety),
        block_relation=f"Ajuste do dia no bloco {block.value} conforme a forma atual.",
        rationale=llm.text if llm.success else "LLM unavailable; ajuste determinístico aplicado.",
        adjust_if_tired="Se mais cansado que o snapshot indica, caia para Z1-Z2 ou descanse.",
        adjust_if_less_time="Com menos tempo, mantenha o bloco principal e corte aquecimento/volume.",
        payload={
            "workout_planned_id": str(workout_planned.id),
            "planned_snapshot": {
                "name": workout_planned.name,
                "structure": workout_planned.structure,
                "planned_tss": workout_planned.planned_tss,
                "planned_duration_s": workout_planned.planned_duration_s,
                "workout_type": getattr(workout_planned.workout_type, "value",
                                        workout_planned.workout_type),
            },
            "adjusted_structure": adjusted_struct,
            "adjusted_tss": adjusted_tss,
            "adjusted_duration_s": adjusted_duration_s,
            "change_summary": result.change_summary,
            "changed": result.changed,
            "signals": signals,
            "llm_text": llm.text,
        },
        risk_level=safety.risk_level, risk_flags=safety.as_dict(),
        confidence=confidence, confidence_rationale=conf_rationale,
        prompt_template_id=template_id, llm_call_id=call_log.id,
        decision=RecommendationDecision.PENDING,
    )
    await RecommendationRepository(session, ctx).add(rec)
    for ev in evidence_builder.to_models(athlete_id, rec.id, evidence_items):
        session.add(ev)
    await session.flush()
    return rec


def _signals(snapshot, methodology: str, block, ftp_watts) -> dict:
    """Traceable inputs that informed the recommendation, surfaced to the
    athlete for transparency (which form/profile signals drove today's call)."""
    def _r(v):
        return round(v, 1) if isinstance(v, (int, float)) else None

    return {
        "form": {
            "ctl": _r(snapshot.ctl),
            "atl": _r(snapshot.atl),
            "tsb": _r(snapshot.tsb),
            "ramp_rate_7d": _r(snapshot.ramp_rate_7d),
            "monotony": _r(snapshot.monotony),
        },
        "methodology": methodology,
        "block": block.value if block is not None else None,
        "ftp_watts": round(ftp_watts) if ftp_watts else None,
    }


def _confidence(risk: RiskLevel, has_evidence: bool) -> tuple[float, str]:
    base = 0.7 if has_evidence else 0.4
    if risk == RiskLevel.HIGH:
        return min(base, 0.5), "High-risk state caps confidence; conservative path chosen."
    if risk == RiskLevel.MODERATE:
        return base - 0.1, "Moderate-risk indicators reduce confidence slightly."
    return base, "Low-risk state with historical evidence supporting the suggestion."


def first_meaningful_line(text: str | None) -> str | None:
    """First non-empty line of ``text`` with leading markdown heading markers
    stripped — keeps raw LLM markdown ('# ...') out of plain-text summaries and
    the calendar's "Motivo:" banner. Returns the input unchanged when falsy."""
    if not text:
        return text
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped
    return None


def _summary(text: str, safety) -> str:
    prefix = ""
    if safety.risk_level == RiskLevel.HIGH:
        prefix = "[CONSERVATIVE ALTERNATIVE — high-risk state] "
    elif safety.risk_level == RiskLevel.MODERATE:
        prefix = "[PROCEED WITH CAUTION] "
    first_line = first_meaningful_line(text) or "Recommendation generated."
    return (prefix + first_line)[:500]


def _objective(safety) -> str:
    if safety.risk_level == RiskLevel.HIGH:
        return "Recovery / load reduction to restore readiness before resuming load."
    return "Targeted stimulus aligned with the current training block and recent load."
