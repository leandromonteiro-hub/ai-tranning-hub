"""garmin_connections table

Revision ID: 0009
Revises: 0008
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_utils import (
    create_index_if_missing,
    create_table_if_missing,
    create_unique_constraint_if_missing,
)
from sqlalchemy.dialects.postgresql import UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table_if_missing(
        "garmin_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("athlete_id", UUID(as_uuid=True), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DISCONNECTED"),
        sa.Column("encrypted_token", sa.Text(), nullable=True),
        sa.Column("mfa_state", sa.Text(), nullable=True),
        sa.Column("mfa_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
    )
    create_index_if_missing("ix_garmin_conn_athlete", "garmin_connections", ["athlete_id"])
    create_unique_constraint_if_missing("uq_garmin_conn_athlete", "garmin_connections", ["athlete_id"])


def downgrade() -> None:
    op.drop_constraint("uq_garmin_conn_athlete", "garmin_connections", type_="unique")
    op.drop_index("ix_garmin_conn_athlete", table_name="garmin_connections")
    op.drop_table("garmin_connections")
