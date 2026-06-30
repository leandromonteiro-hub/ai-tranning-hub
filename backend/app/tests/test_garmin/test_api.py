"""Rotas Garmin: fluxo connect/mfa, status, isolamento por tenant, feature-flag."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_tenant
from app.core.database import get_db
from app.main import app
from app.services.garmin import token_store
from app.services.garmin.fake_client import FakeGarminClient
from app.api.routes import garmin as garmin_routes
from app.tests.conftest import ctx_for


@pytest.fixture
def client_factory(session, two_athletes, monkeypatch):
    a, _ = two_athletes
    monkeypatch.setattr(token_store.settings, "garmin_token_key",
                        __import__("cryptography.fernet", fromlist=["Fernet"])
                        .Fernet.generate_key().decode())
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_tenant] = lambda: ctx_for(a)

    def _make(fake: FakeGarminClient):
        monkeypatch.setattr(garmin_routes, "_new_client", lambda: fake)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
    yield _make
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_connect_needs_mfa_then_completes(client_factory):
    fake = FakeGarminClient(needs_mfa=True)
    async with client_factory(fake) as ac:
        r1 = await ac.post("/api/v1/garmin/connect",
                           json={"email": "e@x.com", "password": "pw"})
        assert r1.status_code == 200
        assert r1.json()["needs_mfa"] is True
        r2 = await ac.post("/api/v1/garmin/connect/mfa", json={"code": "123456"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "CONNECTED"


@pytest.mark.asyncio
async def test_status_reports_connection(client_factory):
    fake = FakeGarminClient(needs_mfa=False)
    async with client_factory(fake) as ac:
        await ac.post("/api/v1/garmin/connect",
                      json={"email": "e@x.com", "password": "pw"})
        r = await ac.get("/api/v1/garmin/status")
        assert r.json()["status"] == "CONNECTED"


@pytest.mark.asyncio
async def test_feature_disabled_returns_503(client_factory, monkeypatch):
    monkeypatch.setattr(token_store.settings, "garmin_token_key", "")
    fake = FakeGarminClient()
    async with client_factory(fake) as ac:
        r = await ac.get("/api/v1/garmin/status")
        assert r.status_code == 503
