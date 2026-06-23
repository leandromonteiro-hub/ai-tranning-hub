"""Populate the global training-knowledge base (documents + embeddings).

Idempotent. Run with `make seed-knowledge`.
"""
from __future__ import annotations

import asyncio

from app.bootstrap import ensure_pgvector
from app.core.database import AsyncSessionLocal
from app.services.knowledge.knowledge_service import (
    ingest_curated_knowledge,
    knowledge_stats,
)


async def main() -> None:
    await ensure_pgvector()
    async with AsyncSessionLocal() as session:
        result = await ingest_curated_knowledge(session)
        await session.commit()
        stats = await knowledge_stats(session)
    print(
        f"Knowledge seeded: +{result['documents_created']} docs / "
        f"+{result['chunks_created']} chunks. "
        f"Total: {stats['documents']} docs, {stats['knowledge_embeddings']} embeddings."
    )


if __name__ == "__main__":
    asyncio.run(main())
