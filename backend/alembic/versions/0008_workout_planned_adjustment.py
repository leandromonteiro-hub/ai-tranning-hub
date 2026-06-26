"""Add adjustment jsonb to workouts_planned (AI day-adjustment override).

Revision ID: 0008
Revises: 0007
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.models.types import jsonb

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workouts_planned", sa.Column("adjustment", jsonb(), nullable=True))


def downgrade() -> None:
    op.drop_column("workouts_planned", "adjustment")
