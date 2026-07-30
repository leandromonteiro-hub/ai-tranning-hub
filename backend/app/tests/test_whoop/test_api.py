"""Rotas Whoop: feature-flag, status, autorização e recusa de callback inválido.

A integração desligada não pode aparecer meio-ligada, e o callback não pode
aceitar código sem state válido — é a única barreira entre o atleta e vincular
sem perceber a conta Whoop de um terceiro.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_tenant
from app.api.routes import whoop as whoop_routes
from app.core.database import get_db
from app.main import app
from app.models.enums import WhoopConnectionStatus
from app.models.whoop import WhoopConnection
from app.services.whoop import token_store
from app.tests.conftest import ctx_for


@pytest.fixture
def athlete_client(session, two_athletes, monkeypatch):
    a, _ = two_athletes
    monkeypatch.setattr(token_store.settings, "whoop_token_key", Fernet.generate_key().decode())
    monkeypatch.setattr(whoop_routes.settings, "whoop_client_id", "cid")
    monkeypatch.setattr(whoop_routes.settings, "whoop_client_secret", "sec")
    monkeypatch.setattr(whoop_routes.settings, "site_address", "app.example")
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_tenant] = lambda: ctx_for(a)
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_status_503_when_not_configured(athlete_client, monkeypatch):
    monkeypatch.setattr(whoop_routes.settings, "whoop_client_id", "")

    async with athlete_client as ac:
        r = await ac.get("/api/v1/whoop/status")

    assert r.status_code == 503


@pytest.mark.asyncio
async def test_status_reports_disconnected_without_a_connection(athlete_client):
    async with athlete_client as ac:
        r = await ac.get("/api/v1/whoop/status")

    assert r.status_code == 200
    assert r.json()["status"] == "DISCONNECTED"


@pytest.mark.asyncio
async def test_authorize_returns_url_with_state_and_redirect(athlete_client):
    async with athlete_client as ac:
        r = await ac.post("/api/v1/whoop/authorize")

    assert r.status_code == 200
    url = r.json()["authorize_url"]
    assert "state=" in url
    assert "app.example%2Fapi%2Fwhoop%2Fcallback" in url


@pytest.mark.asyncio
async def test_callback_rejects_bad_state(athlete_client):
    async with athlete_client as ac:
        r = await ac.post(
            "/api/v1/whoop/callback", json={"code": "abc", "state": "invalido.xx"}
        )

    assert r.status_code == 403
    assert r.json()["detail"] == "invalid_state"


@pytest.mark.asyncio
async def test_sync_refuses_when_not_connected(athlete_client):
    async with athlete_client as ac:
        r = await ac.post("/api/v1/whoop/sync")

    assert r.status_code == 409


@pytest.mark.asyncio
async def test_disconnect_clears_the_token(athlete_client, session, two_athletes):
    a, _ = two_athletes
    session.add(WhoopConnection(
        athlete_id=a.id,
        status=WhoopConnectionStatus.CONNECTED,
        encrypted_token="cipher",
    ))
    await session.flush()

    async with athlete_client as ac:
        r = await ac.delete("/api/v1/whoop/connection")

    assert r.status_code == 204
    conn = (await session.execute(
        __import__("sqlalchemy").select(WhoopConnection).where(
            WhoopConnection.athlete_id == a.id
        )
    )).scalar_one()
    assert conn.status is WhoopConnectionStatus.DISCONNECTED
    assert conn.encrypted_token is None  # o token sai do banco na hora
