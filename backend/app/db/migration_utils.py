"""Ajudantes para migrações tolerarem objetos que já existem.

Por que isto é necessário: a migração 0001 monta o schema com
``Base.metadata.create_all()``, ou seja, a partir dos modelos ATUAIS — não de um
retrato do que existia naquele dia. Num banco vazio ela cria o schema de hoje,
incluindo tudo que as migrações posteriores adicionam, e a cadeia quebra na
primeira que tenta adicionar algo já existente.

Consequência antes disto (descoberta em 2026-07-30): ``alembic upgrade head``
falhava em 0004 num banco vazio. Produção funcionava só porque evoluiu
incrementalmente — ambiente novo, staging e recuperação de desastre estavam
impossibilitados.

Estas funções tornam as migrações idempotentes quanto à EXISTÊNCIA do objeto.
Em produção, onde as migrações já foram aplicadas, elas nunca reexecutam e o
comportamento é idêntico ao anterior.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def table_exists(table: str) -> bool:
    return table in _inspector().get_table_names()


def column_exists(table: str, column: str) -> bool:
    if not table_exists(table):
        return False
    return any(c["name"] == column for c in _inspector().get_columns(table))


def add_column_if_missing(table: str, column: sa.Column) -> bool:
    """Adiciona a coluna só se ela ainda não existir. Devolve True se adicionou."""
    if column_exists(table, column.name):
        return False
    op.add_column(table, column)
    return True


def drop_column_if_exists(table: str, column: str) -> bool:
    if not column_exists(table, column):
        return False
    op.drop_column(table, column)
    return True


def create_table_if_missing(name: str, *columns, **kw) -> bool:
    """Cria a tabela só se ela ainda não existir. Devolve True se criou."""
    if table_exists(name):
        return False
    op.create_table(name, *columns, **kw)
    return True


def index_exists(table: str, name: str) -> bool:
    if not table_exists(table):
        return False
    return any(i["name"] == name for i in _inspector().get_indexes(table))


def create_index_if_missing(
    name: str, table: str, columns: list[str], *, unique: bool = False
) -> bool:
    if index_exists(table, name):
        return False
    op.create_index(name, table, columns, unique=unique)
    return True


def constraint_exists(table: str, name: str) -> bool:
    if not table_exists(table):
        return False
    insp = _inspector()
    named = [c["name"] for c in insp.get_unique_constraints(table)]
    # Um unique criado junto com a tabela pode aparecer como índice único.
    named += [i["name"] for i in insp.get_indexes(table) if i.get("unique")]
    return name in named


def create_unique_constraint_if_missing(name: str, table: str, columns: list[str]) -> bool:
    if constraint_exists(table, name):
        return False
    op.create_unique_constraint(name, table, columns)
    return True
