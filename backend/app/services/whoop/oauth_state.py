"""State assinado do OAuth da Whoop: amarra o callback ao atleta e expira.

Reusa ``settings.jwt_secret_key`` — é o mesmo segredo que já autentica sessão
neste servidor, e um segundo segredo aqui só criaria mais uma coisa para rotacionar.
Efeito colateral desejável: rotacionar o segredo invalida states em trânsito.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid

from app.core.config import settings

TTL_S = 600  # 10 minutos


class WhoopStateError(RuntimeError):
    """State ausente, adulterado, de outro atleta ou expirado."""


def _sign(payload: str) -> str:
    mac = hmac.new(settings.jwt_secret_key.encode(), payload.encode(), hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest()).decode().rstrip("=")


def issue(athlete_id: uuid.UUID) -> str:
    payload = f"{athlete_id}.{int(time.time())}"
    raw = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    return f"{raw}.{_sign(payload)}"


def verify(state: str, athlete_id: uuid.UUID) -> None:
    try:
        raw, sig = state.split(".", 1)
        padded = raw + "=" * (-len(raw) % 4)
        payload = base64.urlsafe_b64decode(padded.encode()).decode()
        claimed_id, _, issued_at = payload.partition(".")
    except (ValueError, UnicodeDecodeError) as exc:
        raise WhoopStateError("state ilegível") from exc

    if not hmac.compare_digest(sig, _sign(payload)):
        raise WhoopStateError("assinatura do state inválida")
    if claimed_id != str(athlete_id):
        raise WhoopStateError("state pertence a outro atleta")
    try:
        if int(issued_at) + TTL_S < int(time.time()):
            raise WhoopStateError("state expirado")
    except ValueError as exc:
        raise WhoopStateError("timestamp do state inválido") from exc
