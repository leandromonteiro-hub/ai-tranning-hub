"""Merge de métricas de recuperação de fontes diferentes numa linha por dia.

``recovery_metrics`` tem uma linha por atleta por dia, então duas pulseiras
disputam as mesmas colunas. Duas regras resolvem:

1. **Vazio nunca apaga.** Um None na resposta da fonte significa "não medi",
   não "o valor é nulo". Antes disso ser explícito, o sync do Garmin apagava HRV
   bom nos dias em que o atleta dormia sem o relógio.
2. **A Whoop tem precedência.** É pulseira usada 24h, feita para medir sono e HRV
   noturno. O Garmin atualiza o que ele mesmo escreveu, mas não encosta em campo
   preenchido de um dia que a Whoop alimentou.

A procedência é por LINHA, não por campo (``source`` acumula os contribuintes do
dia). A consequência aceita está no spec de 2026-07-29.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

from app.models.metrics import RecoveryMetric

PRIORITY_SOURCES: frozenset[str] = frozenset({"whoop"})


@dataclass(frozen=True)
class RecoverySnapshot:
    """Um dia de recuperação, normalizado, independente da fonte."""

    hrv_ms: float | None = None
    resting_hr: int | None = None
    sleep_hours: float | None = None
    sleep_score: float | None = None
    recovery_score: float | None = None


def _row_has_priority_source(source: str | None) -> bool:
    if not source:
        return False
    return any(part in PRIORITY_SOURCES for part in source.split("+"))


def _append_source(current: str | None, incoming: str) -> str:
    parts = [p for p in (current or "").split("+") if p]
    if incoming not in parts:
        parts.append(incoming)
    return "+".join(parts)


def merge_into(row: RecoveryMetric, snap: RecoverySnapshot, source: str) -> bool:
    """Aplica ``snap`` em ``row`` segundo a precedência de ``source``.

    Devolve True se algum campo foi escrito.
    """
    protected = source not in PRIORITY_SOURCES and _row_has_priority_source(row.source)
    changed = False
    for f in fields(snap):
        new = getattr(snap, f.name)
        if new is None:
            continue  # ausência de medida nunca sobrescreve medida
        if protected and getattr(row, f.name) is not None:
            continue  # dia da Whoop: fonte sem precedência só preenche lacuna
        setattr(row, f.name, new)
        changed = True
    if changed:
        row.source = _append_source(row.source, source)
    return changed
