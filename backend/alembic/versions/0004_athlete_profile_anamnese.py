"""Enrich athlete_profiles with anamnese fields.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-23
"""
from __future__ import annotations

import sqlalchemy as sa

from app.db.migration_utils import add_column_if_missing, drop_column_if_exists

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TEXT_COLS = ("goals", "injury_history", "medical_conditions")
_OTHER = (
    ("weekly_hours", sa.Float()),
    ("weekly_days", sa.Integer()),
)
_BOOL_COLS = ("has_power_meter", "has_hr_monitor")


def upgrade() -> None:
    # add_column_if_missing porque a 0001 usa Base.metadata.create_all(): num
    # banco vazio ela já cria estas colunas (ver app/db/migration_utils.py).
    for c in _TEXT_COLS:
        add_column_if_missing("athlete_profiles", sa.Column(c, sa.Text(), nullable=True))
    for name, type_ in _OTHER:
        add_column_if_missing("athlete_profiles", sa.Column(name, type_, nullable=True))
    for c in _BOOL_COLS:
        add_column_if_missing(
            "athlete_profiles",
            sa.Column(c, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    for c in (*_BOOL_COLS, "weekly_days", "weekly_hours", *_TEXT_COLS):
        drop_column_if_exists("athlete_profiles", c)
