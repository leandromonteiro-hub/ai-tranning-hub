"""O token da Whoop nunca fica em claro no banco.

Regressão que este módulo previne: um refresh token vazado dá acesso de leitura
contínuo aos dados de saúde do atleta. Ele só entra na coluna criptografado, e
uma chave ausente falha alto em vez de gravar texto puro.
"""
from __future__ import annotations

import pytest

from app.core import token_crypto
from app.services.whoop import token_store


def test_round_trip_preserves_the_token(monkeypatch):
    monkeypatch.setattr(token_store.settings, "whoop_token_key", _KEY)
    original = {"access_token": "at-123", "refresh_token": "rt-456", "expires_at": 1785000000}

    blob = token_store.encrypt(original)

    assert "at-123" not in blob  # não vaza em claro
    assert token_store.decrypt(blob) == original


def test_missing_key_raises_naming_the_setting(monkeypatch):
    monkeypatch.setattr(token_store.settings, "whoop_token_key", "")

    with pytest.raises(token_store.WhoopCryptoError, match="whoop_token_key"):
        token_store.encrypt({"access_token": "x"})


def test_is_enabled_follows_the_key(monkeypatch):
    monkeypatch.setattr(token_store.settings, "whoop_token_key", "")
    assert token_store.is_enabled() is False
    monkeypatch.setattr(token_store.settings, "whoop_token_key", _KEY)
    assert token_store.is_enabled() is True


def test_garbage_blob_raises_instead_of_returning_junk(monkeypatch):
    monkeypatch.setattr(token_store.settings, "whoop_token_key", _KEY)

    with pytest.raises(token_store.WhoopCryptoError):
        token_store.decrypt("nao-e-um-token-fernet")


def test_shared_layer_keeps_keys_independent():
    """Chave da Whoop não decifra blob do Garmin — o vazamento de uma não expõe a outra."""
    blob = token_crypto.encrypt({"a": 1}, _KEY, "k1")

    with pytest.raises(token_crypto.TokenCryptoError):
        token_crypto.decrypt(blob, _OTHER_KEY, "k2")


_KEY = "t7L24_nBWrRibg21nTLWFq9q2J6lgVW-emXRkl2qggU="
_OTHER_KEY = "Wvb19otj5sWvmbyIB_vRD_7Losff9hk5J_eMDFvqeoA="
