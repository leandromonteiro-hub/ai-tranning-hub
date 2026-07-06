"""SSO Google + convites + onboarding state

Revision ID: 0010
Revises: 0009
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athletes", sa.Column("google_sub", sa.String(length=64), nullable=True))
    op.create_index("ix_athletes_google_sub", "athletes", ["google_sub"], unique=True)
    op.alter_column("athletes", "hashed_password", existing_type=sa.String(length=255), nullable=True)
    op.add_column(
        "athletes",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Atletas existentes não caem no wizard.
    op.execute("UPDATE athletes SET onboarding_completed_at = NOW()")

    op.create_table(
        "invite_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("used_by_athlete_id", UUID(as_uuid=True), sa.ForeignKey("athletes.id"), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_invite_codes_code", "invite_codes", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_invite_codes_code", table_name="invite_codes")
    op.drop_table("invite_codes")
    op.drop_column("athletes", "onboarding_completed_at")
    op.alter_column("athletes", "hashed_password", existing_type=sa.String(length=255), nullable=False)
    op.drop_index("ix_athletes_google_sub", table_name="athletes")
    op.drop_column("athletes", "google_sub")
