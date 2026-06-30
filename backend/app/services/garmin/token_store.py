"""Fernet encryption boundary for Garmin token + MFA client_state at rest.

The ONLY module that handles Garmin secret material's encryption. The athlete's
password is never stored; only the garth token_dict and the in-flight MFA
client_state pass through here, always encrypted with ``settings.garmin_token_key``.
"""
from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class GarminCryptoError(RuntimeError):
    """Raised when encryption/decryption fails or the key is missing."""


def is_enabled() -> bool:
    return bool(settings.garmin_token_key)


def _fernet() -> Fernet:
    if not settings.garmin_token_key:
        raise GarminCryptoError("garmin_token_key is not configured")
    try:
        return Fernet(settings.garmin_token_key.encode())
    except (ValueError, TypeError) as exc:
        raise GarminCryptoError(f"invalid garmin_token_key: {exc}") from exc


def encrypt(data: dict) -> str:
    f = _fernet()
    return f.encrypt(json.dumps(data).encode()).decode()


def decrypt(blob: str) -> dict:
    f = _fernet()
    try:
        return json.loads(f.decrypt(blob.encode()).decode())
    except (InvalidToken, ValueError) as exc:
        raise GarminCryptoError(f"could not decrypt token: {exc}") from exc
