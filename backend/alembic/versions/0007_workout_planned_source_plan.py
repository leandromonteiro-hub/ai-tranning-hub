"""Add source_plan_id to workouts_planned.

Revision ID: 0007
Revises: 0006
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_utils import (
    add_column_if_missing,
    create_index_if_missing,
    drop_column_if_exists,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column_if_missing(
        "workouts_planned",
        sa.Column("source_plan_id", PG_UUID(as_uuid=True), sa.ForeignKey("training_plans.id"), nullable=True),
    )
    create_index_if_missing("ix_workouts_planned_source_plan_id", "workouts_planned", ["source_plan_id"])


def downgrade() -> None:
    op.drop_index("ix_workouts_planned_source_plan_id", table_name="workouts_planned")
    drop_column_if_exists("workouts_planned", "source_plan_id")
