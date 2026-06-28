"""Pure decision logic for polling an async job's Celery state.

Kept free of Streamlit/requests so it can be unit-tested. The caller does the
actual HTTP poll + sleep and feeds the state here each tick."""
from __future__ import annotations

_TERMINAL_OK = "SUCCESS"
_TERMINAL_FAIL = "FAILURE"


def poll_decision(state: str, attempt: int, max_attempts: int) -> str:
    """Return the next action given the job state and how many polls happened.

    - "done"     → state is SUCCESS
    - "failed"   → state is FAILURE
    - "giveup"   → not terminal but attempts reached the cap
    - "continue" → keep polling
    """
    if state == _TERMINAL_OK:
        return "done"
    if state == _TERMINAL_FAIL:
        return "failed"
    if attempt >= max_attempts:
        return "giveup"
    return "continue"
