"""Auto-cadastro por senha gated por convite + login em conta só-Google + claim email."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import safe_decode_token
from app.main import app
from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role
from app.services.auth import invites


@pytest_asyncio.fixture
async def client_and_maker():
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


async def _make_invite(maker) -> str:
    async with maker() as s:
        (inv,) = await invites.create_invites(s, created_by=None, count=1)
        code = inv.code
        await s.commit()
    return code


@pytest.mark.asyncio
async def test_signup_with_valid_invite_creates_athlete(client_and_maker):
    client, maker = client_and_maker
    code = await _make_invite(maker)
    r = await client.post("/api/v1/auth/signup", json={
        "full_name": "Novo Atleta", "email": "novo@x.com",
        "password": "senha12345", "invite_code": code.lower(),
    })
    assert r.status_code == 201
    token = r.json()["access_token"]
    payload = safe_decode_token(token)
    assert payload["email"] == "novo@x.com"  # claim email agora presente
    # convite consumido: segundo uso falha
    r2 = await client.post("/api/v1/auth/signup", json={
        "full_name": "Outro", "email": "outro@x.com",
        "password": "senha12345", "invite_code": code,
    })
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_signup_invalid_invite_403(client_and_maker):
    client, _ = client_and_maker
    r = await client.post("/api/v1/auth/signup", json={
        "full_name": "X", "email": "x@x.com", "password": "senha12345",
        "invite_code": "NAOEXIST",
    })
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_signup_duplicate_email_409(client_and_maker):
    client, maker = client_and_maker
    code1 = await _make_invite(maker)
    code2 = await _make_invite(maker)
    body = {"full_name": "X", "email": "dup@x.com", "password": "senha12345"}
    assert (await client.post("/api/v1/auth/signup", json={**body, "invite_code": code1})).status_code == 201
    r = await client.post("/api/v1/auth/signup", json={**body, "invite_code": code2})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_password_login_on_google_only_account_400(client_and_maker):
    client, maker = client_and_maker
    async with maker() as s:
        s.add(Athlete(email="g@x.com", hashed_password=None, full_name="G",
                      role=Role.ATHLETE, tenant_id="tg", google_sub="g-1"))
        await s.commit()
    r = await client.post("/api/v1/auth/login",
                          data={"username": "g@x.com", "password": "qualquer"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Esta conta usa Entrar com Google."
