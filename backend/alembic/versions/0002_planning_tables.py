"""Phase 4: training plans/blocks/weeks + race_analyses.

Creates only the tables missing from the metadata (create_all uses checkfirst),
so it is safe on databases already at revision 0001.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-23
"""
from __future__ import annotations

from alembic import op

from app.models import Base

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_NEW_TABLES = [
    "training_plans",
    "training_blocks",
    "training_weeks",
    "race_analyses",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in _NEW_TABLES]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in reversed(_NEW_TABLES)]
    Base.metadata.drop_all(bind=bind, tables=tables, checkfirst=True)
