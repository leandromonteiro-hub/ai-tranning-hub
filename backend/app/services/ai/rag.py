"""Minimal RAG retrieval over pgvector.

Custom (no LangChain) so prompt versioning, evidence tracing and call logging
stay fully under our control. Retrieval is strictly partitioned: athlete-private
vectors are filtered by athlete_id; knowledge vectors have athlete_id IS NULL.
The two are never returned by the same query, preventing cross-domain mixing.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Embedding


async def search_knowledge(
    session: AsyncSession, query_vector: list[float], k: int = 5
) -> list[Embedding]:
    """Nearest knowledge-base chunks (athlete_id IS NULL)."""
    stmt = (
        select(Embedding)
        .where(Embedding.athlete_id.is_(None))
        .where(Embedding.deleted_at.is_(None))
        .order_by(Embedding.embedding.cosine_distance(query_vector))
        .limit(k)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def search_athlete_history(
    session: AsyncSession,
    athlete_id: uuid.UUID,
    query_vector: list[float],
    k: int = 5,
) -> list[Embedding]:
    """Nearest athlete-private chunks — strictly scoped to one athlete."""
    stmt = (
        select(Embedding)
        .where(Embedding.athlete_id == athlete_id)
        .where(Embedding.deleted_at.is_(None))
        .order_by(Embedding.embedding.cosine_distance(query_vector))
        .limit(k)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())
