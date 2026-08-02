"""whoop_connections table

Revision ID: 0011
Revises: 0010

Escrita à mão em vez de autogenerate: comparar os modelos contra o banco de
produção traria qualquer drift acumulado para dentro desta migração, e o escopo
aqui é uma tabela nova. Espelha 0009 (garmin_connections) sem os campos de MFA,
que a Whoop não tem.
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

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table_if_missing(
        "whoop_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("athlete_id", UUID(as_uuid=True), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DISCONNECTED"),
        sa.Column("encrypted_token", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
    )
    create_index_if_missing("ix_whoop_conn_athlete", "whoop_connections", ["athlete_id"])
    create_unique_constraint_if_missing("uq_whoop_conn_athlete", "whoop_connections", ["athlete_id"])


def downgrade() -> None:
    op.drop_constraint("uq_whoop_conn_athlete", "whoop_connections", type_="unique")
    op.drop_index("ix_whoop_conn_athlete", table_name="whoop_connections")
    op.drop_table("whoop_connections")
