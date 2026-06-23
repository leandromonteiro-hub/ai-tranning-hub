"""Test fixtures: an in-memory async SQLite DB and two isolated athletes.

SQLite (aiosqlite) keeps the unit/integration tests fast and dependency-free.
The pgvector ``Vector`` column type is swapped for a JSON-compatible type under
SQLite so the schema can be created; vector *search* is exercised separately
against Postgres in integration environments.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.core.tenant import TenantContext
from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # The pgvector-backed `embeddings` table cannot compile under SQLite; it is
    # excluded here and covered by Postgres integration tests instead.
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        yield s


@pytest_asyncio.fixture
async def two_athletes(session) -> tuple[Athlete, Athlete]:
    a = Athlete(
        email="a@example.com", hashed_password=hash_password("pw"),
        full_name="A", role=Role.ATHLETE, tenant_id="tenant_a",
    )
    b = Athlete(
        email="b@example.com", hashed_password=hash_password("pw"),
        full_name="B", role=Role.ATHLETE, tenant_id="tenant_b",
    )
    session.add_all([a, b])
    await session.flush()
    return a, b


def ctx_for(athlete: Athlete) -> TenantContext:
    return TenantContext(
        athlete_id=athlete.id, tenant_id=athlete.tenant_id, role=athlete.role
    )


def admin_ctx() -> TenantContext:
    return TenantContext(athlete_id=uuid.uuid4(), tenant_id="tenant_admin", role=Role.ADMIN)
