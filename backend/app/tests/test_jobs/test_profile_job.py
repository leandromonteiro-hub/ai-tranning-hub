import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.jobs import profile_job


def _fake_redis(acquired: bool):
    """Fake aioredis client whose lock.acquire() returns `acquired`."""
    lock = MagicMock()
    lock.acquire = AsyncMock(return_value=acquired)
    lock.release = AsyncMock()
    client = MagicMock()
    client.lock = MagicMock(return_value=lock)
    client.aclose = AsyncMock()
    return client, lock


@pytest.mark.asyncio
async def test_regenerate_runs_profile_when_lock_acquired():
    aid = str(uuid.uuid4())
    client, lock = _fake_redis(acquired=True)
    fake_session = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_session)
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch.object(profile_job.aioredis, "from_url", return_value=client), \
         patch.object(profile_job, "AsyncSessionLocal", return_value=cm), \
         patch.object(profile_job, "generate_and_persist_profile",
                      new=AsyncMock(return_value={"n_workouts": 42})) as gen:
        out = await profile_job._do_regenerate(aid, "tenant-1")
    gen.assert_awaited_once()
    fake_session.commit.assert_awaited_once()
    lock.release.assert_awaited_once()
    client.aclose.assert_awaited_once()
    assert out == {"status": "done", "n_workouts": 42}


@pytest.mark.asyncio
async def test_regenerate_skips_when_lock_taken():
    aid = str(uuid.uuid4())
    client, lock = _fake_redis(acquired=False)
    with patch.object(profile_job.aioredis, "from_url", return_value=client), \
         patch.object(profile_job, "generate_and_persist_profile",
                      new=AsyncMock()) as gen:
        out = await profile_job._do_regenerate(aid, "tenant-1")
    gen.assert_not_awaited()           # não toca o DB quando já há regen rodando
    lock.release.assert_not_awaited()  # não solta um lock que não pegou
    client.aclose.assert_awaited_once()
    assert out["status"] == "skipped"


def test_task_is_importable_without_broker():
    # O módulo importa e expõe a função mesmo sem Celery/broker.
    assert callable(profile_job.regenerate_profile_task)
