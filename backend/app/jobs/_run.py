"""Helper to run async coroutines inside synchronous Celery tasks."""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Should not happen inside a Celery worker, but be safe.
            return asyncio.run_coroutine_threadsafe(coro, loop).result()
    except RuntimeError:
        pass
    return asyncio.run(coro)
