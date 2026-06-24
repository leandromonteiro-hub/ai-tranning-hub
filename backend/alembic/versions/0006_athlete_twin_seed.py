"""Add twin_seed JSONB to athlete_profiles.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.models.types import jsonb

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_profiles", sa.Column("twin_seed", jsonb(), nullable=True))


def downgrade() -> None:
    op.drop_column("athlete_profiles", "twin_seed")
