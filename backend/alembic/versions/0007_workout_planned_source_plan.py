"""Add source_plan_id to workouts_planned.

Revision ID: 0007
Revises: 0006
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workouts_planned",
        sa.Column("source_plan_id", sa.Uuid(), sa.ForeignKey("training_plans.id"), nullable=True),
    )
    op.create_index("ix_workouts_planned_source_plan_id", "workouts_planned", ["source_plan_id"])


def downgrade() -> None:
    op.drop_index("ix_workouts_planned_source_plan_id", table_name="workouts_planned")
    op.drop_column("workouts_planned", "source_plan_id")
