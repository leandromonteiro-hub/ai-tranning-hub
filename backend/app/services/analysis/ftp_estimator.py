"""FTP estimation and all-time power curve from workout power streams.

This module is pure (no DB, no I/O) so every function is unit-testable in
isolation.  Persistence of FtpHistory / PowerCurvePoint rows happens in
ST2.4.

Public API
----------
all_time_power_curve(power_streams) -> dict[int, float]
    Best mean-maximal power per standard duration across all supplied streams.
    Delegates entirely to :mod:`app.services.metrics.power_curve`.

estimate_ftp_timeline(windows) -> list[FtpEstimate]
    Estimate FTP for each temporal window using 20-min (primary) or 60-min
    (fallback) best power.

Window input shape
------------------
``windows`` is a list of 3-tuples::

    (valid_from: date, valid_to: date | None, power_streams: list[list[float]])

*valid_from*   – inclusive start of the period this FTP covers.
*valid_to*     – inclusive end; ``None`` means "open / current".
*power_streams*– list of 1 Hz power streams (list[float]) for workouts that
                 fall inside the window.  May be empty (window is skipped).

FTP formula
-----------
* Primary   (method ``"estimate_pc20"``): ``ftp = 0.95 × best_20min_power``
  (duration 1200 s).
* Fallback  (method ``"estimate_pc60"``): ``ftp = 0.95 × best_60min_power``
  (duration 3600 s), used when no stream in the window is long enough for a
  20-min window.
* Windows with neither a 20-min nor a 60-min value are silently skipped.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from app.services.metrics.power_curve import (
    DEFAULT_DURATIONS,
    best_mean_maximal,
    power_curve,
)

# Standard durations exposed by power_curve.py (seconds)
_DURATION_20MIN = 1200
_DURATION_60MIN = 3600
_FTP_FACTOR = 0.95


@dataclass(frozen=True)
class FtpEstimate:
    """A single estimated FTP value covering a date range.

    Attributes
    ----------
    valid_from: Start of the period (inclusive).
    valid_to:   End of the period (inclusive); ``None`` = open / current.
    ftp_watts:  Estimated FTP in watts (0.95 × best reference power).
    method:     ``"estimate_pc20"`` or ``"estimate_pc60"``.
    """

    valid_from: date
    valid_to: date | None
    ftp_watts: float
    method: str


def all_time_power_curve(
    power_streams: list[list[float]],
    durations: Sequence[int] = tuple(DEFAULT_DURATIONS),
) -> dict[int, float]:
    """Return the best mean-maximal power per duration across all streams.

    For each standard duration the highest value found in *any* stream wins.
    Durations for which no stream is long enough are absent from the result.

    Parameters
    ----------
    power_streams:
        Each element is a 1 Hz list of power values (floats, watts) for one
        workout.  An empty outer list returns ``{}``.
    durations:
        Sequence of durations in seconds to evaluate.  Defaults to the same
        set used by :func:`~app.services.metrics.power_curve.power_curve`.

    Returns
    -------
    dict[int, float]
        ``{duration_s: best_watts}`` — only durations with at least one valid
        result are included.
    """
    best: dict[int, float] = {}
    for stream in power_streams:
        curve = power_curve(stream, durations=durations)
        for d, val in curve.items():
            if d not in best or val > best[d]:
                best[d] = val
    return best


# Window type alias for readability
_Window = tuple[date, "date | None", list[list[float]]]


def estimate_ftp_timeline(
    windows: list[_Window],
) -> list[FtpEstimate]:
    """Estimate FTP for each temporal window.

    Parameters
    ----------
    windows:
        List of ``(valid_from, valid_to, power_streams)`` tuples.  See module
        docstring for field semantics.

    Returns
    -------
    list[FtpEstimate]
        One entry per window that has sufficient power data, in input order.
        Windows without a 20-min *or* 60-min best power are skipped silently.
    """
    estimates: list[FtpEstimate] = []
    for valid_from, valid_to, streams in windows:
        curve = all_time_power_curve(streams)

        if _DURATION_20MIN in curve:
            ftp = _FTP_FACTOR * curve[_DURATION_20MIN]
            method = "estimate_pc20"
        elif _DURATION_60MIN in curve:
            ftp = _FTP_FACTOR * curve[_DURATION_60MIN]
            method = "estimate_pc60"
        else:
            # No usable reference power in this window — skip
            continue

        estimates.append(
            FtpEstimate(
                valid_from=valid_from,
                valid_to=valid_to,
                ftp_watts=ftp,
                method=method,
            )
        )
    return estimates
