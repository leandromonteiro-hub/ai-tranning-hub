"""Provas de múltiplos dias: races.end_date (NULL = prova de 1 dia).

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa

from app.db.migration_utils import add_column_if_missing, drop_column_if_exists

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column_if_missing("races", sa.Column("end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    drop_column_if_exists("races", "end_date")
