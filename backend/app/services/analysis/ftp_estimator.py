"""FTP estimation and all-time power curve from workout power streams.

This module is pure (no DB, no I/O) so every function is unit-testable in
isolation.  Persistence of FtpHistory / PowerCurvePoint rows happens in
ST2.4.

Public API
----------
is_plausible_power_stream(power_stream, ceiling_20min_w=600.0) -> bool
    Reject corrupt streams (wrong units / device glitch) whose 20-min
    mean-maximal power exceeds a physiological ceiling.

all_time_power_curve(power_streams) -> tuple[dict[int, float], int]
    Best mean-maximal power per standard duration across all *plausible*
    streams, plus the count of streams excluded as implausible.  Delegates
    the mean-max math entirely to :mod:`app.services.metrics.power_curve`.

estimate_ftp_timeline(windows) -> list[FtpEstimate]
    Estimate FTP for each temporal window using 20-min (primary) or 60-min
    (fallback) best power.  Applies the same plausibility filter per window.

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

# Generous physiological ceiling for sustained 20-min power.  No human sustains
# >600 W for 20 min; well above this athlete's ~312 W.  A stream over this is a
# corrupt/wrong-units/device-glitch artifact and must not pollute the curve.
_DEFAULT_CEILING_20MIN_W = 600.0


def is_plausible_power_stream(
    power_stream: Sequence[float],
    ceiling_20min_w: float = _DEFAULT_CEILING_20MIN_W,
) -> bool:
    """Return ``False`` for streams that are physiologically impossible.

    A stream is implausible when its best 20-min (1200 s) mean-maximal power
    exceeds ``ceiling_20min_w`` — a signature of wrong units or a device glitch.

    Streams shorter than 1200 s cannot produce a 20-min inflated value, so they
    are treated as **plausible** here (judged elsewhere by their own duration).
    This keeps the helper focused on the one failure mode that pollutes the
    all-time curve's headline marks.

    Parameters
    ----------
    power_stream:
        1 Hz list of power values (watts).
    ceiling_20min_w:
        Maximum believable 20-min mean-maximal power.  Default 600 W.

    Returns
    -------
    bool
        ``True`` if the stream is plausible (or too short to judge), else
        ``False``.
    """
    best_20 = best_mean_maximal(power_stream, _DURATION_20MIN)
    if best_20 is None:
        # Too short to produce a 20-min value → cannot be the inflation source.
        return True
    return best_20 <= ceiling_20min_w


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
    ceiling_20min_w: float = _DEFAULT_CEILING_20MIN_W,
) -> tuple[dict[int, float], int]:
    """Return the best mean-maximal power per duration across plausible streams.

    Implausible streams (see :func:`is_plausible_power_stream`) are filtered out
    *before* merging so a corrupt/wrong-units stream cannot inflate the
    athlete-facing best marks.  For each standard duration the highest value
    found in any *kept* stream wins; durations for which no kept stream is long
    enough are absent.

    Parameters
    ----------
    power_streams:
        Each element is a 1 Hz list of power values (floats, watts) for one
        workout.  An empty outer list returns ``({}, 0)``.
    durations:
        Sequence of durations in seconds to evaluate.  Defaults to the same
        set used by :func:`~app.services.metrics.power_curve.power_curve`.
    ceiling_20min_w:
        Plausibility ceiling forwarded to :func:`is_plausible_power_stream`.

    Returns
    -------
    tuple[dict[int, float], int]
        ``(curve, excluded)`` where *curve* is ``{duration_s: best_watts}`` and
        *excluded* is the number of streams rejected as implausible.
    """
    best: dict[int, float] = {}
    excluded = 0
    for stream in power_streams:
        if not is_plausible_power_stream(stream, ceiling_20min_w):
            excluded += 1
            continue
        curve = power_curve(stream, durations=durations)
        for d, val in curve.items():
            if d not in best or val > best[d]:
                best[d] = val
    return best, excluded


# Window type alias for readability
_Window = tuple[date, date | None, list[list[float]]]


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
        # all_time_power_curve already filters implausible streams, so a corrupt
        # stream cannot inflate a window's FTP either.
        curve, _excluded = all_time_power_curve(streams)

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
