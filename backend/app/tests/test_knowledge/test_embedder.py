"""Embedder unit tests.

Covers the deterministic mock path at the configured dimension and the
unknown-provider guard. The ``local`` (fastembed) path downloads a ~220MB model
on first use, so it is verified live end-to-end rather than in the unit suite.
"""
from __future__ import annotations

import math

import pytest

from app.core.config import settings
from app.services.knowledge.embedder import _mock_embed, embed_text


def test_mock_embed_matches_configured_dimension_and_is_unit_norm():
    vec = _mock_embed("sweet spot intervals", settings.embedding_dim)
    assert len(vec) == settings.embedding_dim
    assert abs(math.sqrt(sum(v * v for v in vec)) - 1.0) < 1e-6


def test_mock_embed_is_deterministic():
    assert _mock_embed("recovery ride", 384) == _mock_embed("recovery ride", 384)
    assert _mock_embed("a", 384) != _mock_embed("b", 384)


def test_embed_text_uses_mock_provider_by_default():
    # Config default provider is mock; embed_text returns the configured dim.
    assert len(embed_text("Qual treino fazer hoje?")) == settings.embedding_dim


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "bogus")
    with pytest.raises(ValueError):
        embed_text("x")
