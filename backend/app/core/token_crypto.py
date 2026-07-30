"""Criptografia Fernet de material secreto em repouso, com chave por integração.

Único módulo que constrói um Fernet. Cada integração passa a própria chave, para
que o vazamento de uma não exponha as outras. O parâmetro ``name`` existe só para
a mensagem de erro apontar qual setting está faltando.
"""
from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken


class TokenCryptoError(RuntimeError):
    """Criptografia/descriptografia falhou, ou a chave está ausente/inválida."""


def _fernet(key: str, name: str) -> Fernet:
    if not key:
        raise TokenCryptoError(f"{name} is not configured")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise TokenCryptoError(f"invalid {name}: {exc}") from exc


def encrypt(data: dict, key: str, name: str) -> str:
    return _fernet(key, name).encrypt(json.dumps(data).encode()).decode()


def decrypt(blob: str, key: str, name: str) -> dict:
    f = _fernet(key, name)
    try:
        return json.loads(f.decrypt(blob.encode()).decode())
    except (InvalidToken, ValueError) as exc:
        raise TokenCryptoError(f"could not decrypt token: {exc}") from exc
