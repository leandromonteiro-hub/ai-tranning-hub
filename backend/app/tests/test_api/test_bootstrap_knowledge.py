"""Idempotency test for ensure_knowledge / ingest_curated_knowledge.

The ``embeddings`` table uses pgvector's Vector column which cannot be compiled
by SQLite's DDL engine via ORM metadata. We therefore create it manually with a
TEXT column (compatible with pgvector's string-format process_bind_param) so the
first ingest pass can write both knowledge_documents AND embeddings rows, and the
second pass proves the title-based skip prevents any duplicates.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.services.knowledge.knowledge_service import (
    ingest_curated_knowledge,
    knowledge_stats,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def maker():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Step 1: create all ORM-managed tables *except* embeddings (pgvector Vector
    # column cannot be expressed in SQLite DDL via SQLAlchemy metadata).
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    # Step 2: create embeddings manually with TEXT for the vector column.
    # pgvector's Vector.process_bind_param serialises float lists as
    # "[1.0,2.0,…]" strings, which SQLite stores fine in a TEXT column.
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS embeddings (
                id          TEXT PRIMARY KEY,
                created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at  TIMESTAMP,
                created_by  TEXT,
                athlete_id  TEXT,
                namespace   TEXT NOT NULL DEFAULT 'knowledge',
                ref_table   TEXT,
                ref_id      TEXT,
                chunk_text  TEXT NOT NULL,
                embedding   TEXT
            )
        """))

    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


async def test_ingest_is_idempotent(maker):
    async with maker() as s:
        first = await ingest_curated_knowledge(s)
        await s.commit()
    async with maker() as s:
        second = await ingest_curated_knowledge(s)
        await s.commit()
        stats = await knowledge_stats(s)
    assert first["documents_created"] > 0
    assert second["documents_created"] == 0  # nada duplicado na 2ª passada
    assert stats["documents"] == first["documents_created"]


async def test_ensure_knowledge_swallows_failures(maker, monkeypatch):
    """Startup-safety guarantee: a failing ingest must never propagate.

    ensure_knowledge imports ingest_curated_knowledge at function scope from
    knowledge_service, so patching the source module's binding is what the
    deferred import resolves. AsyncSessionLocal is redirected to the in-memory
    sqlite maker so entering the `async with` doesn't touch the real DB.
    """
    import app.bootstrap as bootstrap
    import app.services.knowledge.knowledge_service as ks

    monkeypatch.setattr(bootstrap, "AsyncSessionLocal", maker)

    async def _boom(session):
        raise RuntimeError("boom")

    monkeypatch.setattr(ks, "ingest_curated_knowledge", _boom)

    # must not raise — startup safety guarantee
    assert await bootstrap.ensure_knowledge() is None
