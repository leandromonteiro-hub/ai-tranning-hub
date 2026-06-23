"""Mean-maximal power curve from a power stream."""
from __future__ import annotations

from collections.abc import Sequence

DEFAULT_DURATIONS = [1, 5, 15, 30, 60, 300, 1200, 3600]  # seconds


def best_mean_maximal(
    power_stream: Sequence[float], duration_s: int, sample_hz: float = 1.0
) -> float | None:
    """Best average power sustained over any window of ``duration_s`` seconds."""
    if not power_stream:
        return None
    window = max(1, int(round(duration_s * sample_hz)))
    n = len(power_stream)
    if n < window:
        return None
    running = sum(power_stream[:window])
    best = running
    for i in range(window, n):
        running += power_stream[i] - power_stream[i - window]
        if running > best:
            best = running
    return best / window


def power_curve(
    power_stream: Sequence[float],
    durations: Sequence[int] = tuple(DEFAULT_DURATIONS),
    sample_hz: float = 1.0,
) -> dict[int, float]:
    """Return {duration_s: best_power} for the requested durations present."""
    out: dict[int, float] = {}
    for d in durations:
        val = best_mean_maximal(power_stream, d, sample_hz)
        if val is not None:
            out[d] = val
    return out
