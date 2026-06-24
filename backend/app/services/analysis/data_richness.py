"""Data-richness index for historical training data.

Computes a per-athlete quality/completeness score from their workout and
recovery-day history, used to calibrate AI recommendation confidence.

Weighted blend (score in 0..1)
-------------------------------
  history_breadth  : 0.25  — years_covered capped at 2 years → 0..1
  pct_power        : 0.30  — fraction of completed workouts with avg_power (0..100) → 0..1
  pct_hrv          : 0.20  — fraction of recovery days with hrv_ms (0..100) → 0..1
  workout_count    : 0.15  — COMPLETED-workout count saturating at 300 → 0..1
  pct_sleep        : 0.10  — fraction of recovery days with sleep_hours (0..100) → 0..1
  Total            : 1.00

The workout-count component uses the COMPLETED-workout count (consistent with
pct_power/pct_hr, which also use only completed workouts) so non-completed
workouts cannot inflate the score.  The RichnessIndex.n_workouts field still
reports the TOTAL number of workouts supplied.

Caps / saturation
-----------------
  history_breadth cap  : 2 years  (values above 2 yrs clamped to 1.0)
  workout_count sat.   : 300 workouts  (values above 300 clamped to 1.0)

Label thresholds (score)
------------------------
  < 0.40  → "baixa"
  < 0.70  → "média"
  ≥ 0.70  → "alta"

Inputs are duck-typed (SimpleNamespace, ORM objects, or plain dicts):

  workouts      — objects with .avg_power (float|None), .avg_hr (float|None),
                  .completed (bool, defaults True if attribute absent)
  recovery_days — objects with .hrv_ms (float|None), .sleep_hours (float|None)
  period_start  — date | None
  period_end    — date | None

Pure: no DB/session imports.  Empty inputs are handled gracefully (score 0.0).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Constants (documented above)
# ---------------------------------------------------------------------------

_HISTORY_CAP_YEARS = 2.0
_WORKOUT_COUNT_SAT = 300.0

_W_HISTORY = 0.25
_W_POWER = 0.30
_W_HRV = 0.20
_W_WORKOUT_COUNT = 0.15
_W_SLEEP = 0.10

_LABEL_ALTA = 0.70
_LABEL_MEDIA = 0.40


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass
class RichnessIndex:
    """Summary of an athlete's historical data richness.

    Fields
    ------
    years_covered : float
        Span of the supplied period in years (0 if dates are missing).
    n_workouts : int
        Total number of workouts supplied.
    pct_power : float
        Percentage (0–100) of completed workouts that have a non-null avg_power.
    pct_hr : float
        Percentage (0–100) of completed workouts that have a non-null avg_hr.
    pct_hrv : float
        Percentage (0–100) of recovery days that have a non-null hrv_ms.
    pct_sleep : float
        Percentage (0–100) of recovery days that have a non-null sleep_hours.
    score : float
        Composite richness score in [0, 1] from the documented weighted blend.
    label : str
        Human-readable tier: "baixa" | "média" | "alta".
    """

    years_covered: float
    n_workouts: int
    pct_power: float
    pct_hr: float
    pct_hrv: float
    pct_sleep: float
    score: float
    label: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """Get attribute by name from an object or dict, returning default if absent."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _pct_non_null(items: Sequence[Any], field: str) -> float:
    """Return percentage (0..100) of items where field is not None."""
    if not items:
        return 0.0
    count = sum(1 for item in items if _attr(item, field) is not None)
    return count / len(items) * 100.0


def _completed_workouts(workouts: Sequence[Any]) -> list[Any]:
    """Return only completed workouts (default True when attribute absent)."""
    return [w for w in workouts if _attr(w, "completed", True)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_richness(
    workouts: Sequence[Any],
    recovery_days: Sequence[Any],
    period_start: date | None,
    period_end: date | None,
) -> RichnessIndex:
    """Compute the data-richness index for an athlete.

    Parameters
    ----------
    workouts:
        Duck-typed workout objects with avg_power, avg_hr, and optionally
        completed (bool; treated as True when absent).
    recovery_days:
        Duck-typed recovery-day objects with hrv_ms and sleep_hours.
    period_start:
        Earliest date in the historical window; None if unknown.
    period_end:
        Latest date in the historical window; None if unknown.

    Returns
    -------
    RichnessIndex
        Richness summary with score in [0, 1] and label.
    """
    # --- years_covered ------------------------------------------------------
    if period_start is not None and period_end is not None:
        days = (period_end - period_start).days
        years_covered = days / 365.25
    else:
        years_covered = 0.0

    # --- workout metrics ----------------------------------------------------
    n_workouts = len(workouts)
    completed = _completed_workouts(workouts)

    pct_power = _pct_non_null(completed, "avg_power")
    pct_hr = _pct_non_null(completed, "avg_hr")

    # --- recovery metrics ---------------------------------------------------
    pct_hrv = _pct_non_null(recovery_days, "hrv_ms")
    pct_sleep = _pct_non_null(recovery_days, "sleep_hours")

    # --- score components (each in 0..1) ------------------------------------
    history_component = min(years_covered / _HISTORY_CAP_YEARS, 1.0)
    power_component = pct_power / 100.0
    hrv_component = pct_hrv / 100.0
    # Use the completed-workout count (not the total) so non-completed workouts
    # cannot inflate the score, consistent with the pct_* metrics above.
    workout_component = min(len(completed) / _WORKOUT_COUNT_SAT, 1.0)
    sleep_component = pct_sleep / 100.0

    score = (
        _W_HISTORY * history_component
        + _W_POWER * power_component
        + _W_HRV * hrv_component
        + _W_WORKOUT_COUNT * workout_component
        + _W_SLEEP * sleep_component
    )

    # --- label --------------------------------------------------------------
    if score >= _LABEL_ALTA:
        label = "alta"
    elif score >= _LABEL_MEDIA:
        label = "média"
    else:
        label = "baixa"

    return RichnessIndex(
        years_covered=years_covered,
        n_workouts=n_workouts,
        pct_power=pct_power,
        pct_hr=pct_hr,
        pct_hrv=pct_hrv,
        pct_sleep=pct_sleep,
        score=score,
        label=label,
    )
