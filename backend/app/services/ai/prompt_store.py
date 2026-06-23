"""Persist versioned prompt templates and resolve the active template id.

Recommendations record ``prompt_template_id`` for full auditability. Templates
are upserted from ``prompts.ACTIVE_TEMPLATES`` keyed by (name, content_hash):
editing a template body produces a new hash and a new active version, while the
old version is retained (soft history) for traceability of past recommendations.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import PromptTemplate
from app.services.ai import prompts


async def ensure_templates(session: AsyncSession) -> None:
    """Upsert all active templates. Safe to call repeatedly (idempotent by hash)."""
    for name, (version, body) in prompts.ACTIVE_TEMPLATES.items():
        digest = prompts.template_hash(body)
        existing = await session.execute(
            select(PromptTemplate).where(
                PromptTemplate.name == name,
                PromptTemplate.content_hash == digest,
                PromptTemplate.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            continue
        # New body => deactivate prior active versions of this template.
        prior = await session.execute(
            select(PromptTemplate).where(
                PromptTemplate.name == name,
                PromptTemplate.is_active.is_(True),
                PromptTemplate.deleted_at.is_(None),
            )
        )
        for p in prior.scalars().all():
            p.is_active = False
            session.add(p)
        session.add(
            PromptTemplate(
                name=name, version=version, content_hash=digest, template=body, is_active=True
            )
        )
    await session.flush()


async def active_template_id(session: AsyncSession, name: str) -> uuid.UUID | None:
    res = await session.execute(
        select(PromptTemplate.id).where(
            PromptTemplate.name == name,
            PromptTemplate.is_active.is_(True),
            PromptTemplate.deleted_at.is_(None),
        )
    )
    return res.scalar_one_or_none()
