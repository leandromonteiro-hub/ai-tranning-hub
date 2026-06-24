"""Add extra JSONB to workout tables for source-specific rich fields.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.models.types import jsonb

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("workouts_completed", "workouts_planned"):
        op.add_column(table, sa.Column("extra", jsonb(), nullable=True))


def downgrade() -> None:
    for table in ("workouts_completed", "workouts_planned"):
        op.drop_column(table, "extra")
