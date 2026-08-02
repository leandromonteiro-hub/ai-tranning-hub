"""Remove índices redundantes de athlete_id nas tabelas de conexão.

As migrações 0009 e 0011 criaram `ix_garmin_conn_athlete` e
`ix_whoop_conn_athlete` sobre `athlete_id` — a MESMA coluna que já tem
`UniqueConstraint`, que o Postgres implementa com um índice único. O índice
extra não serve a nenhuma consulta que o único já não sirva; era duplicação
gratuita, e nenhum dos dois nunca existiu nos modelos.

Sintoma que revelou isto: `alembic check` acusava dois `remove_index` de drift
entre o schema migrado e os modelos.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-30
"""
from __future__ import annotations

from alembic import op

from app.db.migration_utils import create_index_if_missing, index_exists

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_REDUNDANT = (
    ("ix_garmin_conn_athlete", "garmin_connections"),
    ("ix_whoop_conn_athlete", "whoop_connections"),
)


def upgrade() -> None:
    for name, table in _REDUNDANT:
        if index_exists(table, name):
            op.drop_index(name, table_name=table)


def downgrade() -> None:
    for name, table in _REDUNDANT:
        create_index_if_missing(name, table, ["athlete_id"])
