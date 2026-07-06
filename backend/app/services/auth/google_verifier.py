"""Verificação de ID token do Google. RealGoogleVerifier é o ÚNICO lugar que
importa google-auth; rotas dependem do Protocol e testam com o Fake."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


class GoogleAuthError(RuntimeError):
    """ID token inválido (assinatura/aud/iss/exp)."""


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str


class GoogleVerifier(Protocol):
    def verify(self, credential: str) -> GoogleIdentity: ...


class RealGoogleVerifier:
    def verify(self, credential: str) -> GoogleIdentity:
        from google.auth.transport import requests as google_requests  # lazy
        from google.oauth2 import id_token

        try:
            info = id_token.verify_oauth2_token(
                credential, google_requests.Request(), settings.google_client_id
            )
        except Exception as exc:  # noqa: BLE001 — qualquer falha => token inválido
            raise GoogleAuthError(f"invalid google credential: {exc}") from exc
        return GoogleIdentity(
            sub=str(info["sub"]),
            email=info.get("email", ""),
            email_verified=bool(info.get("email_verified")),
            name=info.get("name") or info.get("email", ""),
        )


class FakeGoogleVerifier:
    def __init__(self, identity: GoogleIdentity | None = None, error: bool = False):
        self._identity = identity
        self._error = error

    def verify(self, credential: str) -> GoogleIdentity:
        if self._error or self._identity is None:
            raise GoogleAuthError("fake: invalid credential")
        return self._identity
