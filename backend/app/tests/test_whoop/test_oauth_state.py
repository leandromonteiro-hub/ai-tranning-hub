"""O state amarra o callback ao atleta certo e expira.

Sem isso, um atacante induz o atleta logado a abrir um callback com o `code` da
conta Whoop do atacante — e os dados de saúde de um estranho passam a alimentar
o treino do atleta. O state assinado é o que impede.
"""
from __future__ import annotations

import time
import uuid

import pytest

from app.services.whoop import oauth_state


def test_round_trip_accepts_the_same_athlete(monkeypatch):
    monkeypatch.setattr(oauth_state.settings, "jwt_secret_key", "segredo-de-teste")
    aid = uuid.uuid4()

    oauth_state.verify(oauth_state.issue(aid), aid)  # não levanta


def test_rejects_a_different_athlete(monkeypatch):
    monkeypatch.setattr(oauth_state.settings, "jwt_secret_key", "segredo-de-teste")
    state = oauth_state.issue(uuid.uuid4())

    with pytest.raises(oauth_state.WhoopStateError):
        oauth_state.verify(state, uuid.uuid4())


def test_rejects_tampered_state(monkeypatch):
    monkeypatch.setattr(oauth_state.settings, "jwt_secret_key", "segredo-de-teste")
    aid = uuid.uuid4()
    state = oauth_state.issue(aid)

    with pytest.raises(oauth_state.WhoopStateError):
        oauth_state.verify(state[:-4] + "AAAA", aid)


def test_rejects_state_signed_with_another_secret(monkeypatch):
    """Se o segredo do servidor rotacionar, states antigos param de valer."""
    monkeypatch.setattr(oauth_state.settings, "jwt_secret_key", "segredo-antigo")
    aid = uuid.uuid4()
    state = oauth_state.issue(aid)

    monkeypatch.setattr(oauth_state.settings, "jwt_secret_key", "segredo-novo")
    with pytest.raises(oauth_state.WhoopStateError):
        oauth_state.verify(state, aid)


def test_rejects_expired_state(monkeypatch):
    monkeypatch.setattr(oauth_state.settings, "jwt_secret_key", "segredo-de-teste")
    aid = uuid.uuid4()
    monkeypatch.setattr(time, "time", lambda: 1_000_000)
    state = oauth_state.issue(aid)
    monkeypatch.setattr(time, "time", lambda: 1_000_000 + oauth_state.TTL_S + 1)

    with pytest.raises(oauth_state.WhoopStateError):
        oauth_state.verify(state, aid)
