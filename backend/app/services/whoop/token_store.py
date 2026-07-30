"""Fronteira de criptografia do token OAuth da Whoop.

Único módulo que toca o segredo da Whoop em repouso. Access token e refresh token
passam por aqui sempre cifrados com ``settings.whoop_token_key``.
"""
from __future__ import annotations

from app.core import token_crypto
from app.core.config import settings

_KEY_NAME = "whoop_token_key"


class WhoopCryptoError(RuntimeError):
    """Criptografia falhou ou a chave está ausente."""


def is_enabled() -> bool:
    return bool(settings.whoop_token_key)


def encrypt(data: dict) -> str:
    try:
        return token_crypto.encrypt(data, settings.whoop_token_key, _KEY_NAME)
    except token_crypto.TokenCryptoError as exc:
        raise WhoopCryptoError(str(exc)) from exc


def decrypt(blob: str) -> dict:
    try:
        return token_crypto.decrypt(blob, settings.whoop_token_key, _KEY_NAME)
    except token_crypto.TokenCryptoError as exc:
        raise WhoopCryptoError(str(exc)) from exc
