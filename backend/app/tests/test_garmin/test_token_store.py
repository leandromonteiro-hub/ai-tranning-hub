"""token_store: round-trip de cifra Fernet do token/MFA-state do Garmin."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.services.garmin import token_store
from app.services.garmin.token_store import GarminCryptoError


def _key() -> str:
    return Fernet.generate_key().decode()


def test_round_trip_preserves_dict(monkeypatch):
    monkeypatch.setattr(token_store.settings, "garmin_token_key", _key())
    data = {"oauth1": {"token": "abc"}, "oauth2": {"access": "xyz", "expires": 123}}
    blob = token_store.encrypt(data)
    assert isinstance(blob, str)
    assert blob != str(data)  # ciphertext, não plaintext
    assert token_store.decrypt(blob) == data


def test_is_enabled_reflects_key(monkeypatch):
    monkeypatch.setattr(token_store.settings, "garmin_token_key", "")
    assert token_store.is_enabled() is False
    monkeypatch.setattr(token_store.settings, "garmin_token_key", _key())
    assert token_store.is_enabled() is True


def test_encrypt_without_key_raises(monkeypatch):
    monkeypatch.setattr(token_store.settings, "garmin_token_key", "")
    with pytest.raises(GarminCryptoError):
        token_store.encrypt({"a": 1})


def test_decrypt_garbage_raises(monkeypatch):
    monkeypatch.setattr(token_store.settings, "garmin_token_key", _key())
    with pytest.raises(GarminCryptoError):
        token_store.decrypt("not-a-valid-token")
