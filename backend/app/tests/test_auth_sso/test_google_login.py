"""POST /auth/google: login por sub, linking por email verificado, criação com convite."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.routes import auth as auth_routes
from app.core.database import get_db
from app.main import app
from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role
from app.services.auth import invites
from app.services.auth.google_verifier import FakeGoogleVerifier, GoogleIdentity

IDENT = GoogleIdentity(sub="g-42", email="ciclista@gmail.com", email_verified=True, name="Ciclista")


@pytest_asyncio.fixture
async def client_and_maker(monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings.google_client_id", "test-client-id"
    )
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _override_get_db():
        async with maker() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, maker
    app.dependency_overrides.clear()
    await engine.dispose()


def _use_verifier(monkeypatch, verifier):
    monkeypatch.setattr(auth_routes, "_new_verifier", lambda: verifier)


@pytest.mark.asyncio
async def test_new_account_without_invite_403_invite_required(client_and_maker, monkeypatch):
    client, _ = client_and_maker
    _use_verifier(monkeypatch, FakeGoogleVerifier(identity=IDENT))
    r = await client.post("/api/v1/auth/google", json={"credential": "tok"})
    assert r.status_code == 403
    assert r.json()["detail"] == "invite_required"


@pytest.mark.asyncio
async def test_new_account_with_invite_creates_and_logs_in(client_and_maker, monkeypatch):
    client, maker = client_and_maker
    _use_verifier(monkeypatch, FakeGoogleVerifier(identity=IDENT))
    async with maker() as s:
        (inv,) = await invites.create_invites(s, created_by=None, count=1)
        code = inv.code
        await s.commit()
    r = await client.post("/api/v1/auth/google",
                          json={"credential": "tok", "invite_code": code})
    assert r.status_code == 200
    assert "access_token" in r.json()
    # segundo login pelo mesmo sub: sem convite, direto
    r2 = await client.post("/api/v1/auth/google", json={"credential": "tok"})
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_bad_invite_403_invite_invalid(client_and_maker, monkeypatch):
    client, _ = client_and_maker
    _use_verifier(monkeypatch, FakeGoogleVerifier(identity=IDENT))
    r = await client.post("/api/v1/auth/google",
                          json={"credential": "tok", "invite_code": "NAOEXIST"})
    assert r.status_code == 403
    assert r.json()["detail"] == "invite_invalid"


@pytest.mark.asyncio
async def test_links_google_to_existing_password_account(client_and_maker, monkeypatch):
    client, maker = client_and_maker
    _use_verifier(monkeypatch, FakeGoogleVerifier(identity=IDENT))
    async with maker() as s:
        s.add(Athlete(email=IDENT.email, hashed_password="x", full_name="Ja Existia",
                      role=Role.ATHLETE, tenant_id="t-old"))
        await s.commit()
    r = await client.post("/api/v1/auth/google", json={"credential": "tok"})
    assert r.status_code == 200
    async with maker() as s:
        from sqlalchemy import select
        ath = (await s.execute(select(Athlete).where(Athlete.email == IDENT.email))).scalar_one()
        assert ath.google_sub == IDENT.sub


@pytest.mark.asyncio
async def test_unverified_email_does_not_link(client_and_maker, monkeypatch):
    client, maker = client_and_maker
    unverified = GoogleIdentity(sub="g-9", email="x@gmail.com", email_verified=False, name="X")
    _use_verifier(monkeypatch, FakeGoogleVerifier(identity=unverified))
    async with maker() as s:
        s.add(Athlete(email="x@gmail.com", hashed_password="x", full_name="X",
                      role=Role.ATHLETE, tenant_id="t-x"))
        await s.commit()
    r = await client.post("/api/v1/auth/google", json={"credential": "tok"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_invalid_credential_401(client_and_maker, monkeypatch):
    client, _ = client_and_maker
    _use_verifier(monkeypatch, FakeGoogleVerifier(error=True))
    r = await client.post("/api/v1/auth/google", json={"credential": "bad"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_feature_off_503(client_and_maker, monkeypatch):
    client, _ = client_and_maker
    monkeypatch.setattr("app.core.config.settings.google_client_id", "")
    r = await client.post("/api/v1/auth/google", json={"credential": "tok"})
    assert r.status_code == 503
