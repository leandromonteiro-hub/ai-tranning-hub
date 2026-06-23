"""Pure functions for NP, IF, TSS and kJ.

All functions are side-effect free and independently unit-tested. Formulas
follow the standard power-based training metrics (Coggan/TrainingPeaks model).
"""
from __future__ import annotations

import math
from collections.abc import Sequence


def normalized_power(power_stream: Sequence[float], sample_hz: float = 1.0) -> float | None:
    """Normalized Power (NP).

    30-second rolling average of power, raised to the 4th power, averaged,
    then 4th root. Requires roughly >30s of data.
    """
    if not power_stream:
        return None
    window = max(1, int(round(30 * sample_hz)))
    n = len(power_stream)
    if n < window:
        # Not enough data for a true NP; fall back to average power.
        avg = sum(power_stream) / n
        return float(avg)

    # Rolling 30s average via running sum.
    rolling: list[float] = []
    running = sum(power_stream[:window])
    rolling.append(running / window)
    for i in range(window, n):
        running += power_stream[i] - power_stream[i - window]
        rolling.append(running / window)

    fourth = sum(p**4 for p in rolling) / len(rolling)
    return float(fourth ** 0.25)


def intensity_factor(np_value: float | None, ftp: float | None) -> float | None:
    """IF = NP / FTP."""
    if not np_value or not ftp or ftp <= 0:
        return None
    return np_value / ftp


def tss_from_np(
    duration_s: int | None, np_value: float | None, ftp: float | None
) -> float | None:
    """TSS = (duration_s * NP * IF) / (FTP * 3600) * 100."""
    if not duration_s or not np_value or not ftp or ftp <= 0:
        return None
    intf = np_value / ftp
    return (duration_s * np_value * intf) / (ftp * 3600) * 100.0


def tss_from_if(duration_s: int | None, intf: float | None) -> float | None:
    """TSS from an already-known IF: TSS = (duration_h) * IF^2 * 100."""
    if not duration_s or not intf:
        return None
    hours = duration_s / 3600.0
    return hours * (intf**2) * 100.0


def kilojoules(power_stream: Sequence[float], sample_hz: float = 1.0) -> float | None:
    """Total work in kJ = sum(power_w) * dt / 1000."""
    if not power_stream:
        return None
    dt = 1.0 / sample_hz
    return sum(power_stream) * dt / 1000.0


def estimate_tss_from_hr(
    duration_s: int | None,
    avg_hr: float | None,
    resting_hr: float | None,
    max_hr: float | None,
) -> float | None:
    """Fallback hrTSS estimate when no power is available.

    Uses a simple intensity ratio on heart-rate reserve. Clearly an estimate,
    flagged as such by callers so inferred data is never mixed with measured.
    """
    if not duration_s or not avg_hr or not max_hr or not resting_hr:
        return None
    if max_hr <= resting_hr:
        return None
    reserve_ratio = (avg_hr - resting_hr) / (max_hr - resting_hr)
    reserve_ratio = max(0.0, min(1.2, reserve_ratio))
    hours = duration_s / 3600.0
    return hours * (reserve_ratio**2) * 100.0
