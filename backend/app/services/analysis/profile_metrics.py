"""Profile metrics: volume trend, modality split, intensity distribution, best power marks.

This module is **pure** — no DB sessions, no I/O.  Every function accepts plain
Python inputs (dicts or lightweight objects with the needed attributes) so the
full suite is unit-testable with synthetic data.  Persistence and DB wiring are
handled in ST2.4.

Overview of public API
-----------------------
weekly_volume_trend(workouts)          -> WeeklyVolumeTrend
modality_split(workouts)               -> ModalitySplit
intensity_distribution(workouts)       -> IntensityDistribution
best_power_marks(power_curve, weight_kg) -> BestPowerMarks

Input protocol
--------------
Each ``workout`` object only needs the attributes accessed by the function that
consumes it.  You may pass SQLAlchemy model instances, dataclasses, or plain
``types.SimpleNamespace`` objects — duck-typing applies.

Required attributes per function
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
weekly_volume_trend:
    workout_date  : datetime.date
    duration_s    : int | None
    tss           : float | None   (computed tss; may be None)
    extra         : dict | None    (may hold "source_tss": float)
    distance_m    : float | None

modality_split:
    workout_type  : WorkoutType (str-enum value is fine)
    sport         : str
    duration_s    : int | None

intensity_distribution:
    extra         : dict | None  (may hold "pwr_zone_minutes": list[int],
                                  "hr_zone_minutes": list[int])
    intensity_factor : float | None
    duration_s       : int | None

best_power_marks:
    power_curve_dict : dict[int, float]  passed directly as argument
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Protocols — duck-typed input shapes
# ---------------------------------------------------------------------------


@runtime_checkable
class _WorkoutLike(Protocol):
    workout_date: date
    duration_s: int | None
    tss: float | None
    extra: dict | None
    distance_m: float | None
    workout_type: Any
    sport: str
    intensity_factor: float | None


# ---------------------------------------------------------------------------
# Return dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WeeklyVolumePoint:
    """Aggregated metrics for one ISO week.

    Attributes
    ----------
    iso_year:    ISO calendar year (not necessarily the Gregorian year).
    iso_week:    ISO week number 1-53.
    hours:       Total training hours (duration_s / 3600).
    tss:         Total TSS for the week (source_tss preferred over computed tss).
    distance_km: Total distance in km (distance_m / 1000).
    workout_count: Number of workouts in the week.
    """

    iso_year: int
    iso_week: int
    hours: float
    tss: float
    distance_km: float
    workout_count: int


@dataclass
class VolumeTrend:
    """Simple trend summary over the aggregated weekly series.

    Attributes
    ----------
    mean_hours:       Mean weekly hours over the series.
    mean_tss:         Mean weekly TSS over the series.
    direction:        "rising" | "falling" | "stable" — based on slope of
                      hours over the last vs first half of the period.  A
                      change of less than 5 % from mean is "stable".
    weeks_analysed:   Number of weeks in the series.
    """

    mean_hours: float
    mean_tss: float
    direction: str  # "rising" | "falling" | "stable"
    weeks_analysed: int


@dataclass
class WeeklyVolumeTrend:
    """Full result of :func:`weekly_volume_trend`.

    Attributes
    ----------
    weeks:  Chronologically ordered list of weekly aggregates.
    trend:  Simple trend summary; None when fewer than 2 weeks of data.
    """

    weeks: list[WeeklyVolumePoint]
    trend: VolumeTrend | None


# -----------

@dataclass
class SportShare:
    """Workout/time share for one sport category.

    Attributes
    ----------
    sport:           Normalised sport label (e.g. "cycling", "swim", "strength").
    workout_count:   Number of workouts.
    total_hours:     Total duration in hours.
    pct_workouts:    Fraction of total workout count (0-1).
    pct_hours:       Fraction of total hours (0-1).
    """

    sport: str
    workout_count: int
    total_hours: float
    pct_workouts: float
    pct_hours: float


@dataclass
class WorkoutTypeShare:
    """Workout/time share for one WorkoutType.

    Attributes
    ----------
    workout_type:    WorkoutType value as a string.
    workout_count:   Number of workouts.
    total_hours:     Total duration in hours.
    pct_workouts:    Fraction of total workout count (0-1).
    pct_hours:       Fraction of total hours (0-1).
    """

    workout_type: str
    workout_count: int
    total_hours: float
    pct_workouts: float
    pct_hours: float


@dataclass
class ModalitySplit:
    """Full result of :func:`modality_split`.

    Attributes
    ----------
    by_sport:        List of :class:`SportShare`, sorted by workout count desc.
    by_workout_type: List of :class:`WorkoutTypeShare`, sorted by count desc.
    total_workouts:  Grand total (denominator for % calcs).
    total_hours:     Grand total hours.
    """

    by_sport: list[SportShare]
    by_workout_type: list[WorkoutTypeShare]
    total_workouts: int
    total_hours: float


# -----------

@dataclass
class MeasuredZones:
    """Zone-minute aggregates sourced from TrainingPeaks own zone splits.

    ``source = "trainingpeaks"`` — these are *measured* values as exported by
    TP; they reflect whatever zone model the athlete's TP account uses (typically
    Coggan 7-zone for power, 5-zone for HR).

    Attributes
    ----------
    source:               Always "trainingpeaks".
    pwr_zone_minutes:     Total minutes per power zone index 0-9 across all
                          workouts.  Index corresponds to TP zone order (0=Z1…).
                          Zones absent from every workout have 0 minutes.
    hr_zone_minutes:      Same for heart-rate zones.
    workouts_with_power_zones: Count of workouts that had pwr_zone_minutes data.
    workouts_with_hr_zones:    Count of workouts that had hr_zone_minutes data.
    """

    source: str = "trainingpeaks"
    pwr_zone_minutes: list[int] = field(default_factory=lambda: [0] * 10)
    hr_zone_minutes: list[int] = field(default_factory=lambda: [0] * 10)
    workouts_with_power_zones: int = 0
    workouts_with_hr_zones: int = 0


@dataclass
class DerivedZones:
    """3-zone intensity classification derived by us from Intensity Factor (IF).

    ``source = "derived_if"`` — inferred from IF using the mapping below; NOT a
    measured value.

    3-zone model (Seiler / polarised framework):
      Z1 (low):       IF < 0.75   → Z1_recovery + Z2_endurance in Coggan terms
      Z2 (threshold): 0.75 ≤ IF < 0.90 → Z3_tempo + Z4_threshold in Coggan terms
      Z3 (high):      IF ≥ 0.90   → Z5_vo2max and above in Coggan terms

    Intensity distribution label rules (applied to % of *hours* in each zone):
      polarized:   Z1 ≥ 75 % AND Z3 ≥ 10 % AND Z2 < 20 %
      sweet_spot:  Z2 ≥ 35 % (significant emphasis on threshold/tempo work)
      pyramidal:   Z1 > Z2 > Z3  (descending but not polarised)
      mixed:       does not fit any of the above (fallback)

    Attributes
    ----------
    source:          Always "derived_if".
    z1_hours:        Hours classified as Z1.
    z2_hours:        Hours classified as Z2.
    z3_hours:        Hours classified as Z3.
    unclassified_hours: Hours without a valid IF (cannot be classified).
    z1_pct:          Fraction of classifiable hours in Z1 (0-1).
    z2_pct:          Fraction of classifiable hours in Z2 (0-1).
    z3_pct:          Fraction of classifiable hours in Z3 (0-1).
    distribution_label: "polarized" | "pyramidal" | "sweet_spot" | "mixed".
    workouts_classified: Number of workouts with a valid IF.

    Note: z1_pct/z2_pct/z3_pct are rounded to 4 decimal places and may not sum
    to exactly 1.0 (e.g. a 3-way even split rounds to 0.9999).
    """

    source: str = "derived_if"
    z1_hours: float = 0.0
    z2_hours: float = 0.0
    z3_hours: float = 0.0
    unclassified_hours: float = 0.0
    z1_pct: float = 0.0
    z2_pct: float = 0.0
    z3_pct: float = 0.0
    distribution_label: str = "mixed"
    workouts_classified: int = 0


@dataclass
class IntensityDistribution:
    """Full result of :func:`intensity_distribution`.

    Attributes
    ----------
    measured:  Zone totals from TrainingPeaks data (``source = "trainingpeaks"``).
    derived:   Our 3-zone classification from IF (``source = "derived_if"``).
    """

    measured: MeasuredZones
    derived: DerivedZones


# -----------

@dataclass
class PowerMark:
    """Best power for a single duration.

    Attributes
    ----------
    duration_s:  Duration in seconds.
    watts:       Best mean-maximal power for that duration.
    w_per_kg:    Watts per kilogram; None when no weight is available.
    """

    duration_s: int
    watts: float
    w_per_kg: float | None


@dataclass
class BestPowerMarks:
    """Full result of :func:`best_power_marks`.

    Attributes
    ----------
    marks:      One :class:`PowerMark` per requested standard duration.  Only
                durations present in the input power_curve are included.
    weight_kg:  The weight used for W/kg, or None.
    """

    marks: list[PowerMark]
    weight_kg: float | None


# ---------------------------------------------------------------------------
# Helper: normalise sport label
# ---------------------------------------------------------------------------

_CYCLING_SPORTS = {"cycling", "bike", "mtb", "mountain biking", "road cycling",
                   "gravel", "cyclocross", "cx", "velodrome", "track"}


def _normalise_sport(raw: str) -> str:
    """Map raw sport strings to normalised labels used in ModalitySplit."""
    lower = raw.lower().strip()
    if lower in _CYCLING_SPORTS or "bike" in lower or "cycl" in lower:
        return "cycling"
    if "swim" in lower or "pool" in lower:
        return "swim"
    if "strength" in lower or "gym" in lower or "weight" in lower or ("force" in lower and "run" not in lower):
        return "strength"
    if "run" in lower or "trail" in lower:
        return "running"
    return lower if lower else "other"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def weekly_volume_trend(workouts: list[Any]) -> WeeklyVolumeTrend:
    """Aggregate workouts into ISO-week buckets and compute a simple trend.

    Parameters
    ----------
    workouts:
        Iterable of workout-like objects.  Required attributes per object:
        ``workout_date``, ``duration_s``, ``tss``, ``extra``, ``distance_m``.
        See module docstring for full protocol.

    Returns
    -------
    WeeklyVolumeTrend
        ``weeks`` sorted chronologically; ``trend`` is None when fewer than 2
        weeks of data.

    TSS precedence
    --------------
    ``extra["source_tss"]`` (TP's own TSS) is preferred over the model's
    computed ``tss`` field, matching the project convention for data provenance.
    """
    # Accumulate per (iso_year, iso_week)
    buckets: dict[tuple[int, int], dict[str, float]] = {}

    for w in workouts:
        d: date = w.workout_date
        iso = d.isocalendar()
        key = (iso[0], iso[1])

        if key not in buckets:
            buckets[key] = {"hours": 0.0, "tss": 0.0, "distance_km": 0.0, "count": 0.0}

        dur = w.duration_s or 0
        buckets[key]["hours"] += dur / 3600.0

        # TSS: prefer source_tss from extra (TP measured), fall back to computed
        extra = w.extra or {}
        tss_val = extra.get("source_tss") or w.tss or 0.0
        buckets[key]["tss"] += float(tss_val)

        dist = w.distance_m or 0.0
        buckets[key]["distance_km"] += dist / 1000.0

        buckets[key]["count"] += 1.0

    weeks = [
        WeeklyVolumePoint(
            iso_year=k[0],
            iso_week=k[1],
            hours=round(v["hours"], 3),
            tss=round(v["tss"], 1),
            distance_km=round(v["distance_km"], 2),
            workout_count=int(v["count"]),
        )
        for k, v in sorted(buckets.items())
    ]

    if len(weeks) < 2:
        return WeeklyVolumeTrend(weeks=weeks, trend=None)

    total_hours = sum(w.hours for w in weeks)
    total_tss = sum(w.tss for w in weeks)
    n = len(weeks)
    mean_hours = total_hours / n
    mean_tss = total_tss / n

    # Slope from first-half mean vs second-half mean
    mid = n // 2
    first_half_mean = sum(w.hours for w in weeks[:mid]) / mid
    second_half_mean = sum(w.hours for w in weeks[mid:]) / (n - mid)

    threshold = 0.05 * mean_hours  # 5 % of mean
    if abs(second_half_mean - first_half_mean) < threshold:
        direction = "stable"
    elif second_half_mean > first_half_mean:
        direction = "rising"
    else:
        direction = "falling"

    trend = VolumeTrend(
        mean_hours=round(mean_hours, 3),
        mean_tss=round(mean_tss, 1),
        direction=direction,
        weeks_analysed=n,
    )

    return WeeklyVolumeTrend(weeks=weeks, trend=trend)


def modality_split(workouts: list[Any]) -> ModalitySplit:
    """Compute share of workouts and time by sport and by workout_type.

    Parameters
    ----------
    workouts:
        Iterable of workout-like objects.  Required attributes:
        ``workout_type``, ``sport``, ``duration_s``.

    Returns
    -------
    ModalitySplit
        Both splits normalised to percentages of total count and total hours.
    """
    sport_counts: dict[str, int] = {}
    sport_hours: dict[str, float] = {}
    type_counts: dict[str, int] = {}
    type_hours: dict[str, float] = {}

    for w in workouts:
        sport = _normalise_sport(str(w.sport or "other"))
        wtype = str(w.workout_type) if w.workout_type is not None else "OTHER"
        # Strip enum class prefix if present (e.g. "WorkoutType.ENDURANCE")
        if "." in wtype:
            wtype = wtype.rsplit(".", 1)[-1]
        hours = (w.duration_s or 0) / 3600.0

        sport_counts[sport] = sport_counts.get(sport, 0) + 1
        sport_hours[sport] = sport_hours.get(sport, 0.0) + hours
        type_counts[wtype] = type_counts.get(wtype, 0) + 1
        type_hours[wtype] = type_hours.get(wtype, 0.0) + hours

    # Real totals (exposed on the dataclass) kept separate from the division
    # denominators (which guard against division by zero on empty input).
    total = sum(sport_counts.values())
    total_h = sum(sport_hours.values())
    sport_denom = total or 1
    sport_h_denom = total_h or 1.0
    type_denom = sum(type_counts.values()) or 1
    type_h_denom = sum(type_hours.values()) or 1.0

    by_sport = sorted(
        [
            SportShare(
                sport=s,
                workout_count=sport_counts[s],
                total_hours=round(sport_hours[s], 3),
                pct_workouts=round(sport_counts[s] / sport_denom, 4),
                pct_hours=round(sport_hours[s] / sport_h_denom, 4),
            )
            for s in sport_counts
        ],
        key=lambda x: x.workout_count,
        reverse=True,
    )

    by_type = sorted(
        [
            WorkoutTypeShare(
                workout_type=t,
                workout_count=type_counts[t],
                total_hours=round(type_hours[t], 3),
                pct_workouts=round(type_counts[t] / type_denom, 4),
                pct_hours=round(type_hours[t] / type_h_denom, 4),
            )
            for t in type_counts
        ],
        key=lambda x: x.workout_count,
        reverse=True,
    )

    return ModalitySplit(
        by_sport=by_sport,
        by_workout_type=by_type,
        total_workouts=total,
        total_hours=round(total_h, 3),
    )


# ---------------------------------------------------------------------------
# IF thresholds for 3-zone classification
# ---------------------------------------------------------------------------
_IF_Z1_UPPER = 0.75   # IF < 0.75   → Zone 1 (low / endurance)
_IF_Z2_UPPER = 0.90   # 0.75 ≤ IF < 0.90 → Zone 2 (threshold / sweet-spot)
# IF ≥ 0.90 → Zone 3 (high / VO2max+)

# Distribution label thresholds
_POLARIZED_Z1_MIN = 0.75
_POLARIZED_Z3_MIN = 0.10
_POLARIZED_Z2_MAX = 0.20
_SWEET_SPOT_Z2_MIN = 0.35


def _label_distribution(z1_pct: float, z2_pct: float, z3_pct: float) -> str:
    """Classify the 3-zone distribution into a named pattern.

    Rules (applied in order, first match wins):
    1. polarized:   Z1 ≥ 75 % AND Z3 ≥ 10 % AND Z2 < 20 %
    2. sweet_spot:  Z2 ≥ 35 %
    3. pyramidal:   Z1 > Z2 > Z3
    4. mixed:       fallback

    These rules are intentionally simple and documented; no claim is made that
    they capture every nuance of real periodisation science.
    """
    if z1_pct >= _POLARIZED_Z1_MIN and z3_pct >= _POLARIZED_Z3_MIN and z2_pct < _POLARIZED_Z2_MAX:
        return "polarized"
    if z2_pct >= _SWEET_SPOT_Z2_MIN:
        return "sweet_spot"
    if z1_pct > z2_pct > z3_pct:
        return "pyramidal"
    return "mixed"


def intensity_distribution(workouts: list[Any]) -> IntensityDistribution:
    """Compute two views of intensity distribution.

    View 1 — MEASURED (source="trainingpeaks"):
        Aggregate ``extra["pwr_zone_minutes"]`` and ``extra["hr_zone_minutes"]``
        across all workouts.  These values are TrainingPeaks' own zone split for
        each workout.  Up to 10 zones per channel are supported.

    View 2 — DERIVED (source="derived_if"):
        Classify each workout into a 3-zone model from its ``intensity_factor``
        (IF) using fixed thresholds.  The overall distribution is then labelled
        as polarized / pyramidal / sweet_spot / mixed.

    Parameters
    ----------
    workouts:
        Iterable of workout-like objects.  Required attributes:
        ``extra``, ``intensity_factor``, ``duration_s``.

    Returns
    -------
    IntensityDistribution
    """
    # --- MEASURED ---
    measured = MeasuredZones()
    for w in workouts:
        extra = w.extra or {}

        pwr = extra.get("pwr_zone_minutes")
        if pwr and isinstance(pwr, (list, tuple)):
            measured.workouts_with_power_zones += 1
            for i, mins in enumerate(pwr[:10]):
                measured.pwr_zone_minutes[i] += int(mins or 0)

        hr = extra.get("hr_zone_minutes")
        if hr and isinstance(hr, (list, tuple)):
            measured.workouts_with_hr_zones += 1
            for i, mins in enumerate(hr[:10]):
                measured.hr_zone_minutes[i] += int(mins or 0)

    # --- DERIVED ---
    z1_hours = 0.0
    z2_hours = 0.0
    z3_hours = 0.0
    unclassified_hours = 0.0
    workouts_classified = 0

    for w in workouts:
        dur_h = (w.duration_s or 0) / 3600.0
        if_ = w.intensity_factor
        if if_ is None or if_ <= 0:
            unclassified_hours += dur_h
            continue
        workouts_classified += 1
        if if_ < _IF_Z1_UPPER:
            z1_hours += dur_h
        elif if_ < _IF_Z2_UPPER:
            z2_hours += dur_h
        else:
            z3_hours += dur_h

    classifiable = z1_hours + z2_hours + z3_hours
    if classifiable > 0:
        z1_pct = z1_hours / classifiable
        z2_pct = z2_hours / classifiable
        z3_pct = z3_hours / classifiable
        label = _label_distribution(z1_pct, z2_pct, z3_pct)
    else:
        z1_pct = z2_pct = z3_pct = 0.0
        label = "mixed"

    derived = DerivedZones(
        z1_hours=round(z1_hours, 3),
        z2_hours=round(z2_hours, 3),
        z3_hours=round(z3_hours, 3),
        unclassified_hours=round(unclassified_hours, 3),
        z1_pct=round(z1_pct, 4),
        z2_pct=round(z2_pct, 4),
        z3_pct=round(z3_pct, 4),
        distribution_label=label,
        workouts_classified=workouts_classified,
    )

    return IntensityDistribution(measured=measured, derived=derived)


# Standard durations for best-power marks (seconds)
_BEST_POWER_DURATIONS = (5, 60, 300, 1200, 3600)


def best_power_marks(
    power_curve_dict: dict[int, float],
    weight_kg: float | None = None,
) -> BestPowerMarks:
    """Extract best power marks at standard durations from the all-time power curve.

    Parameters
    ----------
    power_curve_dict:
        ``{duration_s: watts}`` mapping as produced by
        :func:`~app.services.analysis.ftp_estimator.all_time_power_curve`.
        Durations not in the dict are silently skipped.
    weight_kg:
        Athlete body weight in kilograms.  When provided, W/kg is computed for
        each mark.  ``None`` → W/kg fields are omitted (``None``).

    Returns
    -------
    BestPowerMarks
        One :class:`PowerMark` per matching duration, in ascending duration
        order.  Only durations present in *both* the standard list and the
        supplied dict are returned.
    """
    marks: list[PowerMark] = []
    for dur in _BEST_POWER_DURATIONS:
        if dur not in power_curve_dict:
            continue
        watts = power_curve_dict[dur]
        w_per_kg = round(watts / weight_kg, 3) if weight_kg is not None and weight_kg > 0 else None
        marks.append(PowerMark(duration_s=dur, watts=watts, w_per_kg=w_per_kg))

    return BestPowerMarks(marks=marks, weight_kg=weight_kg)
