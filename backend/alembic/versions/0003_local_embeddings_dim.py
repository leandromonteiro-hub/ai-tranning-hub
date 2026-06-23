"""Switch embedding vectors to 384 dims (local multilingual model).

The embedding pipeline moves from the 1536-dim placeholder to a 384-dim local
fastembed model. A pgvector column's dimension is fixed at creation, so the
``embeddings.embedding`` column must be dropped and recreated. The embeddings
(and the curated knowledge documents that produce them) are fully re-seedable,
so both tables are truncated here and repopulated by ``seed_knowledge`` with
real vectors afterwards.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Pinned to the local multilingual model's dimension (see app/core/config.py).
_NEW_DIM = 384
_OLD_DIM = 1536


def _recreate_embedding_column(dim: int) -> None:
    # Truncate re-seedable content: clearing the embedding column requires an
    # empty table (a NOT NULL column can't be added to populated rows), and the
    # knowledge documents must be cleared too so seed_knowledge regenerates them.
    op.execute("TRUNCATE TABLE embeddings, knowledge_documents")
    op.drop_column("embeddings", "embedding")
    op.add_column("embeddings", sa.Column("embedding", Vector(dim), nullable=False))


def upgrade() -> None:
    _recreate_embedding_column(_NEW_DIM)


def downgrade() -> None:
    _recreate_embedding_column(_OLD_DIM)
