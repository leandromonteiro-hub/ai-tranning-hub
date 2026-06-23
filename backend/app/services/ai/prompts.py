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
Athlete digital-twin snapshot:
{twin}

Safety guardrail result (already computed — respect it):
{safety}

Relevant historical evidence (the athlete's own data):
{evidence}

Relevant training-knowledge context:
{knowledge}

Athlete question / request:
{question}

Produce a single recommendation as structured guidance including: the
physiological objective, how it relates to the current block and target race,
the supporting evidence, a confidence level (0-1) with justification, identified
risks, how to scale down if the athlete is more tired, and how to scale down if
they have less time available today.
"""


def render_daily_workout(
    twin: str, safety: str, evidence: str, knowledge: str, question: str
) -> str:
    return DAILY_WORKOUT_TEMPLATE.format(
        twin=twin, safety=safety, evidence=evidence,
        knowledge=knowledge, question=question or "Recommend today's workout.",
    )


def template_hash(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


# Registry of active templates (name -> (version, body)).
ACTIVE_TEMPLATES = {
    "daily_workout": (1, DAILY_WORKOUT_TEMPLATE),
}
