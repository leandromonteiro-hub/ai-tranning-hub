"""Initial schema: pgvector extension + all core tables.

This bootstrap migration enables the ``vector`` extension and then creates the
full set of tables from the SQLAlchemy metadata. Subsequent schema changes
should use normal ``alembic revision --autogenerate`` diffs.

Revision ID: 0001
Revises:
Create Date: 2026-06-22
"""
from __future__ import annotations

from alembic import op

from app.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # pgvector must exist before the embeddings table (Vector column) is created.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
