"""Helper to run async coroutines inside synchronous Celery tasks."""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any


async def _dispose_engine_after(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run the coroutine, then dispose the global engine pool IN THE SAME LOOP.

    Each run_async() call spins a fresh event loop (asyncio.run). asyncpg
    connections created by task N stay in the module-level engine pool bound to
    task N's (now closed) loop; task N+1 checking one out dies with
    "attached to a different loop". Disposing per task keeps the pool empty
    across loops at the cost of a reconnect per job — negligible at job cadence.
    """
    try:
        return await coro
    finally:
        from app.core.database import engine  # local import — avoid import cycle

        await engine.dispose()


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Should not happen inside a Celery worker, but be safe. The loop
            # outlives this call, so the pool stays valid — no dispose needed.
            return asyncio.run_coroutine_threadsafe(coro, loop).result()
    except RuntimeError:
        pass
    return asyncio.run(_dispose_engine_after(coro))
