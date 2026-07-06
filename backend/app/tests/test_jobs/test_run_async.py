"""run_async must dispose the global engine pool after every task-loop.

Regression: two consecutive Celery tasks in one worker process each get a
fresh event loop (asyncio.run). Without a per-task engine.dispose(), asyncpg
connections pooled by task N (bound to its closed loop) are checked out by
task N+1 and crash with "attached to a different loop" — seen live 2026-07-06
(garmin_sync succeeded, then garmin_push_recommendation blew up).
"""
from __future__ import annotations

from app.core import database
from app.jobs._run import run_async


class _StubEngine:
    def __init__(self) -> None:
        self.disposed = 0

    async def dispose(self) -> None:
        self.disposed += 1


def test_run_async_returns_value_and_disposes_engine(monkeypatch):
    stub = _StubEngine()
    monkeypatch.setattr(database, "engine", stub)

    async def work():
        return 42

    assert run_async(work()) == 42
    assert stub.disposed == 1


def test_run_async_disposes_even_when_coro_raises(monkeypatch):
    stub = _StubEngine()
    monkeypatch.setattr(database, "engine", stub)

    async def boom():
        raise ValueError("job failed")

    try:
        run_async(boom())
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError to propagate")
    assert stub.disposed == 1
