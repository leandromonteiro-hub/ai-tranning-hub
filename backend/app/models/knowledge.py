"""Training knowledge base, embeddings (pgvector) and versioned prompt templates.

The knowledge base is GLOBAL (not athlete-scoped) and is never mixed with an
athlete's real data. Embeddings carry an optional athlete_id: NULL = general
knowledge document, set = an athlete-private vector (workout/race/comment).
"""
from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.models.base import Base
from app.models.types import jsonb


class KnowledgeDocument(Base):
    """A conceptual training-methodology document (global reference)."""

    __tablename__ = "knowledge_documents"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)


class Embedding(Base):
    """A vector embedding for semantic search (RAG).

    athlete_id NULL  -> general knowledge (knowledge_documents)
    athlete_id set   -> athlete-private content (kept isolated at query time)
    """

    __tablename__ = "embeddings"

    # Nullable tenant key: NULL means a global/knowledge embedding.
    athlete_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("athletes.id"), index=True, nullable=True
    )
    namespace: Mapped[str] = mapped_column(String(32), default="knowledge")  # knowledge/workout/race/comment
    ref_table: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))


class PromptTemplate(Base):
    """Versioned prompt template with content hash for auditability."""

    __tablename__ = "prompt_templates"

    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
