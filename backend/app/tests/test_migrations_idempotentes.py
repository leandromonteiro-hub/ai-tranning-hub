"""Impede que uma migração nova volte a quebrar a subida de um banco vazio.

A 0001 monta o schema com ``Base.metadata.create_all()``, a partir dos modelos
ATUAIS. Num banco vazio ela já cria tudo que as migrações posteriores adicionam
— então qualquer ``op.add_column``/``op.create_table``/``op.create_index`` cru
depois dela estoura com "already exists" e a cadeia inteira para.

Isso aconteceu de verdade: em 2026-07-30 ``alembic upgrade head`` falhava na
0004 num banco vazio. Produção seguia funcionando só porque evoluiu
incrementalmente; ambiente novo, staging e recuperação de desastre estavam
impossibilitados, e ninguém percebeu porque nada testava a cadeia do zero.

O teste é estático (a suíte roda em SQLite e não consegue executar a cadeia,
que precisa de pgvector). Ele não prova que as migrações aplicam — prova que
ninguém reintroduziu a construção que quebrou.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"

# op.<nome> que falha se o objeto já existir. Cada um tem equivalente
# tolerante em app/db/migration_utils.py.
_CRUS = {
    "add_column": "add_column_if_missing",
    "create_table": "create_table_if_missing",
    "create_index": "create_index_if_missing",
    "create_unique_constraint": "create_unique_constraint_if_missing",
}

# Dispensas, com o motivo. Uma migração nova NÃO entra aqui sem justificativa:
# se ela precisa de um op cru, provavelmente vai quebrar o banco vazio.
_DISPENSADAS = {
    # Recria a coluna de embedding com outra dimensão: o add vem logo depois de
    # um drop_column na mesma função, então nunca encontra a coluna existente.
    "0003_local_embeddings_dim.py",
}


def _ops_crus(caminho: Path) -> list[str]:
    """Devolve os `op.<nome>` proibidos chamados no arquivo, com a linha."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    achados = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
            continue
        alvo = no.func
        if isinstance(alvo.value, ast.Name) and alvo.value.id == "op" and alvo.attr in _CRUS:
            achados.append(f"linha {no.lineno}: op.{alvo.attr}() — use {_CRUS[alvo.attr]}()")
    return achados


@pytest.mark.parametrize(
    "caminho",
    sorted(p for p in _VERSIONS.glob("0*.py") if p.name not in _DISPENSADAS),
    ids=lambda p: p.name,
)
def test_migracao_nao_usa_op_cru(caminho: Path) -> None:
    achados = _ops_crus(caminho)
    assert not achados, (
        f"{caminho.name} usa DDL que estoura se o objeto já existir "
        f"(ver app/db/migration_utils.py):\n  " + "\n  ".join(achados)
    )


def test_o_detector_enxerga_um_op_cru(tmp_path: Path) -> None:
    """Sem isto, o teste acima passaria mesmo com o detector quebrado."""
    falso = tmp_path / "0099_ruim.py"
    falso.write_text(
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        "def upgrade():\n"
        "    op.add_column('athletes', sa.Column('x', sa.Text()))\n",
        encoding="utf-8",
    )
    achados = _ops_crus(falso)
    assert len(achados) == 1
    assert "add_column_if_missing" in achados[0]
