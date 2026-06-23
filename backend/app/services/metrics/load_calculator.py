"""CTL / ATL / TSB and Foster monotony/strain from a daily TSS series.

Pure, deterministic functions over date->TSS maps. The exponential model uses
the standard Performance Manager constants (CTL 42d, ATL 7d).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

CTL_TIME_CONSTANT = 42
ATL_TIME_CONSTANT = 7


@dataclass
class DailyLoad:
    metric_date: date
    daily_tss: float
    ctl: float
    atl: float
    tsb: float
    monotony: float | None = None
    strain: float | None = None


def _alpha(time_constant: int) -> float:
    return 1.0 - pow(2.718281828459045, -1.0 / time_constant)


def compute_load_series(
    tss_by_date: dict[date, float],
    start: date | None = None,
    end: date | None = None,
    seed_ctl: float = 0.0,
    seed_atl: float = 0.0,
) -> list[DailyLoad]:
    """Compute the daily CTL/ATL/TSB series, filling gaps (rest days = 0 TSS).

    TSB for a given day uses yesterday's CTL-ATL (standard PMC convention).
    """
    if not tss_by_date and start is None:
        return []

    all_dates = sorted(tss_by_date.keys())
    start = start or all_dates[0]
    end = end or all_dates[-1]

    ctl_alpha = _alpha(CTL_TIME_CONSTANT)
    atl_alpha = _alpha(ATL_TIME_CONSTANT)

    series: list[DailyLoad] = []
    ctl = seed_ctl
    atl = seed_atl
    prev_ctl = ctl
    prev_atl = atl

    d = start
    while d <= end:
        tss = float(tss_by_date.get(d, 0.0))
        # TSB = yesterday's fitness - fatigue.
        tsb = prev_ctl - prev_atl
        ctl = ctl + ctl_alpha * (tss - ctl)
        atl = atl + atl_alpha * (tss - atl)
        series.append(
            DailyLoad(metric_date=d, daily_tss=tss, ctl=ctl, atl=atl, tsb=tsb)
        )
        prev_ctl, prev_atl = ctl, atl
        d += timedelta(days=1)

    _attach_monotony_strain(series)
    return series


def _attach_monotony_strain(series: list[DailyLoad]) -> None:
    """Foster monotony (mean/sd) and strain (weekly load * monotony), 7d window."""
    for i, day in enumerate(series):
        window = [s.daily_tss for s in series[max(0, i - 6) : i + 1]]
        if len(window) < 2:
            continue
        mean = statistics.mean(window)
        sd = statistics.pstdev(window)
        if sd == 0:
            monotony = None
        else:
            monotony = mean / sd
        day.monotony = monotony
        if monotony is not None:
            day.strain = sum(window) * monotony


def ramp_rate(series: list[DailyLoad], days: int = 7) -> float | None:
    """CTL change over the last ``days`` (a ramp-rate / fitness gain proxy)."""
    if len(series) <= days:
        return None
    return series[-1].ctl - series[-1 - days].ctl
