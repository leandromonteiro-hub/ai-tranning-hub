"""Versioned prompt templates with content hashing for auditability."""
from __future__ import annotations

import hashlib

SYSTEM_PROMPT = (
    "You are an evidence-based endurance cycling coach assistant. You only reason "
    "from the athlete's own historical data and the provided training-knowledge "
    "context. You never exceed a 10% weekly load increase, never ignore fatigue, "
    "sleep or HRV signals, and you clearly separate measured facts from inferred "
    "suggestions. You are an analytical support tool and never replace medical or "
    "professional evaluation. Every recommendation must be explainable and tied to "
    "the evidence provided."
)

DAILY_WORKOUT_TEMPLATE = """\
Athlete profile (anamnese — who this athlete is):
{profile}

Athlete training methodology (reverse-engineered from the athlete's real
training history — match their established intensity distribution, periodization
patterns and power profile unless safety requires otherwise):
{methodology}

Athlete digital-twin snapshot:
{twin}

Safety guardrail result (already computed — respect it):
{safety}

Relevant historical evidence (the athlete's own data):
{evidence}

Relevant training-knowledge context:
{knowledge}

Athlete feedback on recent recommendations (respect what worked; adjust what
was rated poorly — never promise results, never override the safety guardrail):
{feedback}

Traditional-method workout (what this athlete's own historical methodology would
prescribe today — reverse-engineered from their real training):
{methodology_workout}

When you write the recommendation, explicitly CONTRAST your recommended session
with this traditional-method one: name what the traditional method would do, then
what you recommend and WHY it differs (or say plainly if they coincide today).

Athlete question / request:
{question}

Produce a single recommendation as structured guidance including: the
physiological objective, how it relates to the current block and target race,
the supporting evidence, a confidence level (0-1) with justification, identified
risks, how to scale down if the athlete is more tired, and how to scale down if
they have less time available today. Tailor it to the athlete profile and to the
athlete's established training methodology above (intensity distribution,
periodization, power profile, experience, goals, availability, injuries).
"""


def render_daily_workout(
    twin: str, safety: str, evidence: str, knowledge: str, question: str,
    profile: str = "n/d", methodology: str = "n/d", feedback: str = "n/d",
    methodology_workout: str = "n/d",
) -> str:
    return DAILY_WORKOUT_TEMPLATE.format(
        profile=profile, methodology=methodology, twin=twin, safety=safety,
        evidence=evidence, knowledge=knowledge, feedback=feedback,
        methodology_workout=methodology_workout,
        question=question or "Recommend today's workout.",
    )


def template_hash(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


# Registry of active templates (name -> (version, body)).
ACTIVE_TEMPLATES = {
    "daily_workout": (5, DAILY_WORKOUT_TEMPLATE),
}
