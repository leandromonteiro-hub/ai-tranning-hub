"""Fronteira de criptografia do token Garmin + client_state do MFA em repouso.

A senha do atleta nunca é guardada; só o token_dict do garth e o client_state de
MFA em trânsito passam por aqui, sempre cifrados com ``settings.garmin_token_key``.
A criptografia em si vive em ``app.core.token_crypto`` — compartilhada com a Whoop
para não haver duas implementações de Fernet no projeto.
"""
from __future__ import annotations

from app.core import token_crypto
from app.core.config import settings

_KEY_NAME = "garmin_token_key"


class GarminCryptoError(RuntimeError):
    """Raised when encryption/decryption fails or the key is missing."""


def is_enabled() -> bool:
    return bool(settings.garmin_token_key)


def encrypt(data: dict) -> str:
    try:
        return token_crypto.encrypt(data, settings.garmin_token_key, _KEY_NAME)
    except token_crypto.TokenCryptoError as exc:
        raise GarminCryptoError(str(exc)) from exc


def decrypt(blob: str) -> dict:
    try:
        return token_crypto.decrypt(blob, settings.garmin_token_key, _KEY_NAME)
    except token_crypto.TokenCryptoError as exc:
        raise GarminCryptoError(str(exc)) from exc
