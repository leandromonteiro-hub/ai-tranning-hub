"""Ingest curated knowledge documents into the global knowledge base.

Creates one ``knowledge_documents`` row per concept and one ``embeddings`` row
per chunk (athlete_id IS NULL => global knowledge). Idempotent: a document whose
title already exists is skipped. Embeddings are produced by the configured
embedder (mock by default, swappable for a real model).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.knowledge import Embedding, KnowledgeDocument
from app.services.knowledge.document_loader import CURATED_DOCUMENTS, chunk_text
from app.services.knowledge.embedder import embed_text

log = get_logger(__name__)


async def ingest_curated_knowledge(session: AsyncSession) -> dict:
    """Seed the knowledge base from the curated documents. Returns a summary."""
    created_docs = 0
    created_chunks = 0

    for doc in CURATED_DOCUMENTS:
        exists = await session.execute(
            select(KnowledgeDocument.id).where(
                KnowledgeDocument.title == doc.title,
                KnowledgeDocument.deleted_at.is_(None),
            )
        )
        if exists.scalar_one_or_none():
            continue

        kd = KnowledgeDocument(
            title=doc.title, category=doc.category, content=doc.content, source=doc.source
        )
        session.add(kd)
        await session.flush()
        created_docs += 1

        for chunk in chunk_text(doc.content):
            session.add(
                Embedding(
                    athlete_id=None,  # global knowledge — never tenant-scoped
                    namespace="knowledge",
                    ref_table="knowledge_documents",
                    ref_id=kd.id,
                    chunk_text=f"{doc.title}: {chunk}",
                    embedding=embed_text(f"{doc.title}: {chunk}"),
                )
            )
            created_chunks += 1

    await session.flush()
    log.info("knowledge_ingested", extra={"documents": created_docs, "chunks": created_chunks})
    return {"documents_created": created_docs, "chunks_created": created_chunks}


async def knowledge_stats(session: AsyncSession) -> dict:
    docs = await session.execute(
        select(func.count()).select_from(KnowledgeDocument).where(
            KnowledgeDocument.deleted_at.is_(None)
        )
    )
    embs = await session.execute(
        select(func.count()).select_from(Embedding).where(
            Embedding.athlete_id.is_(None), Embedding.deleted_at.is_(None)
        )
    )
    return {"documents": int(docs.scalar() or 0), "knowledge_embeddings": int(embs.scalar() or 0)}
