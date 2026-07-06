"""FakeGoogleVerifier: contrato do Protocol usado pelas rotas (Real é adapter de rede)."""
from __future__ import annotations

import pytest

from app.services.auth.google_verifier import (
    FakeGoogleVerifier,
    GoogleAuthError,
    GoogleIdentity,
)


def test_fake_returns_configured_identity():
    ident = GoogleIdentity(sub="g-123", email="x@gmail.com", email_verified=True, name="X")
    fake = FakeGoogleVerifier(identity=ident)
    assert fake.verify("any-credential") == ident


def test_fake_raises_when_configured_as_error():
    fake = FakeGoogleVerifier(error=True)
    with pytest.raises(GoogleAuthError):
        fake.verify("bad")


def test_settings_default_google_client_id_empty():
    from app.core.config import Settings
    assert Settings(_env_file=None).google_client_id == ""
