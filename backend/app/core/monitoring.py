"""Ping de um monitor externo (healthchecks.io). Único ponto que sai para a rede.

Regra que governa este módulo: um monitor NUNCA pode derrubar o job que ele
monitora. Toda exceção é engolida e logada como warning.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0


def ping_monitor(
    url: str | None,
    suffix: str = "",
    body: str | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> bool:
    """POST no check do monitor externo. Devolve True só se o ping saiu (2xx).

    url:       URL do check. Vazia/None => no-op silencioso (retorna False).
    suffix:    "/fail" para sinalizar falha em vez de sucesso.
    body:      corpo opcional (aparece no alerta do healthchecks.io).
    transport: costura de teste (httpx.MockTransport). Produção não passa.
    """
    if not url:
        return False

    target = f"{url.rstrip('/')}{suffix}" if suffix else url
    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS, transport=transport) as client:
            response = client.post(target, content=body or b"")
        if response.is_success:
            return True
        logger.warning("monitor ping returned %s for %s", response.status_code, target)
        return False
    except Exception as exc:  # noqa: BLE001 — monitor nunca derruba o job
        logger.warning("monitor ping failed for %s: %r", target, exc)
        return False
