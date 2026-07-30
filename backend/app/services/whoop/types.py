"""Tipos e erros do domínio Whoop. Nenhuma exceção da httpx atravessa esta camada."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.services.recovery.merge import RecoverySnapshot


class WhoopAuthError(RuntimeError):
    """Token inválido, expirado ou revogado — exige reautenticação do atleta."""


class WhoopSyncError(RuntimeError):
    """Falha não-autenticação numa chamada (rede, 5xx, corpo inesperado)."""


class WhoopRateLimited(WhoopSyncError):
    """429 da Whoop. ``retry_after_s`` vem do cabeçalho X-RateLimit-Reset."""

    def __init__(self, message: str, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


@dataclass(frozen=True)
class WhoopDay:
    """Um dia de recuperação da Whoop, já resolvido para data local."""

    metric_date: date
    snapshot: RecoverySnapshot
