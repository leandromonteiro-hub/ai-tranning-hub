"""Methodology reverse-engineering: block detection, race detection, taper windows,
and coach-comment term frequency.

This module is **pure** — no DB sessions, no I/O.  Every function accepts plain
Python inputs (dicts or lightweight objects with the needed attributes) so the
full suite is unit-testable with synthetic data.  DB loading happens in ST2.4.

Overview of public API
-----------------------
detect_blocks(load_metrics)              -> list[Block]
detect_races(workouts)                   -> list[Race]
taper_windows(races, load_metrics)       -> list[TaperWindow]
coach_comment_terms(workouts, top_n=30) -> list[tuple[str, int]]

Detection rules (documented here as the canonical spec)
-------------------------------------------------------
detect_blocks
~~~~~~~~~~~~~
Input chronological daily load metrics (metric_date, ctl, atl, tsb, daily_tss).
The timeline is segmented into non-overlapping blocks using a sliding-window
classification on weekly aggregates:

1. Weekly TSS is computed from daily_tss per ISO-week bucket.
2. 4-week rolling CTL slope is computed for each week.
3. Classification (first match wins per week; weeks then merged into blocks).
   TAPER is evaluated BEFORE RECOVERY so a deliberate pre-race taper (CTL near
   peak, TSB rising, gentle CTL decline) is not mis-labelled as recovery:
   - TAPER     : TSB rising strongly (last_tsb - first_tsb > 2) AND
                  weekly TSS < TAPER_TSS_THRESHOLD (< 400 TSS/week) AND
                  week-start CTL at or near peak (>= TAPER_CTL_NEAR_PEAK % of
                  max CTL seen) AND CTL ramp vs prev week >= -3.5 (gentle decline)
   - RECOVERY  : weekly TSS < RECOVERY_TSS_THRESHOLD (< 200 TSS/week) OR
                  CTL ramp rate < RECOVERY_RAMP_THRESHOLD (< -1.5 CTL/week)
   - PEAK      : CTL is at the highest point in the series (local maximum) AND
                  weekly TSS >= TAPER_TSS_THRESHOLD
   - BUILD     : CTL ramp rate >= BUILD_RAMP_THRESHOLD (>= 0.7 CTL/week) AND
                  weekly TSS >= BUILD_TSS_THRESHOLD (>= 420 TSS/week)
   - BASE      : CTL ramp rate >= BASE_RAMP_THRESHOLD (>= 0.2 CTL/week) — default
                  when none of the above match

Consecutive weeks with the same label are merged into a single Block.
Evidence cites the CTL range, date range, and mean weekly TSS for the block.

detect_races
~~~~~~~~~~~~
A workout is flagged as a race if ANY of the following is true:
1. workout_type == 'RACE' (or WorkoutType.RACE enum value) — primary catch.
2. Name (case-insensitive) contains any of:
   prova, race, maratona, xco, xcm, cup, copa, gp, campeonato — primary catch.
3. (Fallback) TSS spike RELATIVE to this athlete's own workouts AND a high IF.
   The threshold is self-contained: derived from the workout list itself as
   ``tss_threshold = max(percentile_90(completed_workout_tss), 150.0)`` and the
   IF gate is ``intensity_factor >= RACE_IF_SPIKE (0.85)``.  This avoids missing
   short, high-intensity MTB/XCO races (TSS often only ~100-150) that an
   absolute spike threshold would skip, while still excluding ordinary hard
   training days.

Evidence cites the reason (enum type / keyword matched / tss+IF values).
Deduplication: one Race per date (earliest matching workout wins).

taper_windows
~~~~~~~~~~~~~
For each race, look back up to TAPER_LOOKBACK_DAYS (21) days before race_date.
Collect the matching load_metrics.  Compute:
- ctl_start  : CTL at the first available metric in the window
- ctl_race   : CTL on race_date (or the last available metric before)
- atl_race   : ATL on race_date
- tsb_race   : TSB on race_date
- weekly_tss_trend : list of weekly TSS sums (up to 3 weeks) in the window,
                     chronological order
Evidence cites the CTL drop/change and TSB on race day.

coach_comment_terms
~~~~~~~~~~~~~~~~~~~
Aggregate all coach_comments strings from workout.extra["coach_comments"].
Normalise to lowercase, split on word boundaries, remove:
- Portuguese stopwords (hardcoded small set below)
- Single-character tokens
- Pure digits

Terms in the cycling domain whitelist (z2, z3, vo2, ftp, limiar, etc.) bypass
any length filter.  Return the top_n most common (term, count) tuples, sorted
by count descending.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.models.enums import WorkoutType

# ===========================================================================
# Return dataclasses
# ===========================================================================


@dataclass(frozen=True)
class Block:
    """A detected training block.

    Attributes
    ----------
    start:      First date of the block (inclusive).
    end:        Last date of the block (inclusive).
    block_type: One of "base", "build", "peak", "taper", "recovery".
    evidence:   Human-readable string citing the specific CTL/TSS numbers and
                dates that justify the classification.  Always non-empty;
                always contains at least one numeric value.
    """

    start: date
    end: date
    block_type: str
    evidence: str


@dataclass(frozen=True)
class Race:
    """A detected race event.

    Attributes
    ----------
    date:     Date the race occurred.
    name:     Name of the workout (may be empty string for unnamed workouts).
    evidence: Why this was flagged (enum type / keyword / TSS spike).
              Always non-empty; contains the triggering value.
    """

    date: date
    name: str
    evidence: str


@dataclass
class TaperWindow:
    """Pre-race CTL/ATL/TSB reconstruction.

    Attributes
    ----------
    race_date:        Date of the race.
    ctl_start:        CTL at the beginning of the lookback window.
    ctl_race:         CTL on (or closest before) race_date.
    atl_race:         ATL on (or closest before) race_date.
    tsb_race:         TSB on (or closest before) race_date.
    weekly_tss_trend: Weekly TSS sums in chronological order (up to 3 values).
    evidence:         Summary of CTL change and TSB on race day.
    """

    race_date: date
    ctl_start: float
    ctl_race: float
    atl_race: float
    tsb_race: float
    weekly_tss_trend: list[float] = field(default_factory=list)
    evidence: str = ""


# ===========================================================================
# Thresholds / tuneable constants (documented per rule above)
# ===========================================================================

# detect_blocks thresholds
_RECOVERY_TSS_THRESHOLD = 200.0       # weekly TSS below this → recovery
_RECOVERY_RAMP_THRESHOLD = -1.5       # CTL/week slope below this → recovery
_TAPER_TSS_THRESHOLD = 400.0          # weekly TSS below this (+ TSB rising) → taper
_TAPER_CTL_NEAR_PEAK_PCT = 0.95       # within 95 % of max CTL seen → near peak
_BUILD_RAMP_THRESHOLD = 0.7           # CTL/week slope at or above this → build
_BUILD_TSS_THRESHOLD = 420.0          # weekly TSS at or above this → build
_BASE_RAMP_THRESHOLD = 0.2            # CTL/week slope at or above this → base (default)

# detect_races thresholds
_RACE_KEYWORDS = {
    "prova", "race", "maratona", "xco", "xcm", "cup", "copa", "gp", "campeonato"
}
# Rule 3 (fallback) uses a RELATIVE TSS threshold derived from the workout list
# itself: max(p90 of completed-workout TSS, _RACE_TSS_SPIKE_FLOOR).  The IF gate
# stays absolute.
_RACE_TSS_SPIKE_FLOOR = 150.0   # never go below this even for low-volume athletes
_RACE_TSS_PERCENTILE = 90       # percentile of the athlete's own TSS distribution
_RACE_IF_SPIKE = 0.85

# taper_windows
_TAPER_LOOKBACK_DAYS = 21


# ===========================================================================
# Stopword set for coach_comment_terms
# ===========================================================================

_PORTUGUESE_STOPWORDS: frozenset[str] = frozenset({
    "de", "e", "o", "a", "os", "as", "da", "do", "das", "dos",
    "em", "para", "que", "com", "um", "uma", "no", "na", "nos", "nas",
    "se", "por", "ao", "aos", "sua", "seu", "seus", "suas",
    "ou", "mas", "mais", "já", "ja", "bem", "bom", "ser",
    "foi", "não", "nao", "ele", "ela", "eles", "elas",
    "esse", "essa", "isso", "isto", "aqui",
    "muito", "pouco", "hoje", "ontem", "amanha",
    "treino", "treinar",  # too generic for methodology
    "dia", "semana", "mes",
})

# Cycling domain terms that bypass the length filter
_CYCLING_WHITELIST: frozenset[str] = frozenset({
    "z1", "z2", "z3", "z4", "z5", "z6", "z7",
    "ftp", "vo2", "if", "tss", "ctl", "atl", "tsb",
    "hr", "rpe",
    "limiar", "sprint", "cadencia", "cadence",
    "sweet", "spot", "fadiga", "recuperacao", "recovery",
    "base", "build", "peak", "taper",
    "aerobico", "anaerobico", "threshold", "endurance", "tempo",
    "intervalo", "series", "repeticoes",
    "descida", "subida", "climb", "flat",
    "ritmo", "pacing", "volume", "intensidade",
})


# ===========================================================================
# Internal helpers
# ===========================================================================

def _week_key(d: date) -> tuple[int, int]:
    """Return (iso_year, iso_week) for a date."""
    iso = d.isocalendar()
    return (iso[0], iso[1])


def _aggregate_weekly(
    metrics: list[Any],
) -> list[dict]:
    """Aggregate daily metrics into ISO-week buckets.

    Returns a list of dicts with keys:
    week_key, start_date, end_date, total_tss, mean_ctl_start, mean_ctl_end,
    first_ctl, last_ctl, first_tsb, last_tsb
    """
    buckets: dict[tuple[int, int], dict] = {}
    for m in metrics:
        key = _week_key(m.metric_date)
        if key not in buckets:
            buckets[key] = {
                "week_key": key,
                "dates": [],
                "ctls": [],
                "tsbs": [],
                "total_tss": 0.0,
            }
        b = buckets[key]
        b["dates"].append(m.metric_date)
        b["ctls"].append(m.ctl)
        b["tsbs"].append(m.tsb)
        b["total_tss"] += m.daily_tss

    result = []
    for key in sorted(buckets):
        b = buckets[key]
        b["dates"].sort()
        result.append({
            "week_key": key,
            "start_date": b["dates"][0],
            "end_date": b["dates"][-1],
            "total_tss": b["total_tss"],
            "first_ctl": b["ctls"][0],
            "last_ctl": b["ctls"][-1],
            "first_tsb": b["tsbs"][0],
            "last_tsb": b["tsbs"][-1],
            "n_days": len(b["dates"]),
        })
    return result


def _classify_week(
    week: dict,
    prev_week: dict | None,
    max_ctl_seen: float,
) -> str:
    """Classify a single week into a block type string.

    Parameters
    ----------
    week:          Aggregated week dict (from _aggregate_weekly).
    prev_week:     Previous week dict, or None for the first week.
    max_ctl_seen:  The highest CTL value observed across the entire series.

    Returns
    -------
    One of: "recovery", "taper", "peak", "build", "base"
    """
    weekly_tss = week["total_tss"]
    # Scale weekly TSS by actual days to avoid penalising partial weeks at boundaries
    n_days = max(week["n_days"], 1)
    # Normalise to 7-day equivalent
    weekly_tss_normalised = weekly_tss * (7 / n_days)

    # CTL ramp vs the previous week's last CTL (falls back to the within-week
    # change for the first week, which has no predecessor).
    if prev_week is not None:
        ctl_ramp_vs_prev = week["last_ctl"] - prev_week["last_ctl"]
    else:
        ctl_ramp_vs_prev = week["last_ctl"] - week["first_ctl"]

    # --- TAPER: TSB improving strongly, moderate-low TSS, CTL was near peak ---
    # Check BEFORE recovery so that a planned taper (CTL near peak, TSB rising)
    # is not mis-classified as recovery even when the CTL slope turns negative.
    # We use the *start* of the week CTL (before the TSS drop deflates it) to
    # determine whether this is a taper descent from a peak, not recovery.
    # The ramp guard distinguishes a deliberate taper (gentle CTL decline,
    # ctl_ramp_vs_prev >= -3.5) from a full recovery week (fast CTL drop).
    _TAPER_MAX_RAMP_DROP = -3.5
    tsb_strongly_rising = week["last_tsb"] - week["first_tsb"] > 2.0
    ctl_was_near_peak = week["first_ctl"] >= max_ctl_seen * _TAPER_CTL_NEAR_PEAK_PCT
    if (
        tsb_strongly_rising
        and weekly_tss_normalised < _TAPER_TSS_THRESHOLD
        and ctl_was_near_peak
        and ctl_ramp_vs_prev >= _TAPER_MAX_RAMP_DROP
    ):
        return "taper"

    # --- RECOVERY: very low TSS or strongly negative ramp ---
    if weekly_tss_normalised < _RECOVERY_TSS_THRESHOLD or ctl_ramp_vs_prev < _RECOVERY_RAMP_THRESHOLD:
        return "recovery"

    # --- PEAK: CTL at or near maximum and TSS is still substantial ---
    if (
        week["last_ctl"] >= max_ctl_seen * _TAPER_CTL_NEAR_PEAK_PCT
        and weekly_tss_normalised >= _TAPER_TSS_THRESHOLD
    ):
        return "peak"

    # --- BUILD: fast CTL ramp and high TSS ---
    if ctl_ramp_vs_prev >= _BUILD_RAMP_THRESHOLD and weekly_tss_normalised >= _BUILD_TSS_THRESHOLD:
        return "build"

    # --- BASE: moderate CTL ramp (default for positive ramp periods) ---
    return "base"


# ===========================================================================
# Public API
# ===========================================================================


def detect_blocks(load_metrics: list[Any]) -> list[Block]:
    """Segment a chronological series of daily load metrics into training blocks.

    Parameters
    ----------
    load_metrics:
        Chronologically ordered list of daily load-metric objects.  Each must
        expose: ``metric_date`` (date), ``ctl`` (float), ``atl`` (float),
        ``tsb`` (float), ``daily_tss`` (float).

    Returns
    -------
    list[Block]
        Non-overlapping, chronologically ordered blocks.  Each block carries an
        ``evidence`` string that cites the CTL range, mean weekly TSS, and date
        span of the block.

    Rules
    -----
    See module docstring for the full decision tree.  In brief:

    1. Aggregate daily metrics into ISO-week buckets.
    2. Classify each week using CTL slope, weekly TSS, and TSB trend.
    3. Merge consecutive same-label weeks into a single Block.
    4. Build evidence string from the aggregated numbers.
    """
    if not load_metrics:
        return []

    weeks = _aggregate_weekly(load_metrics)
    if not weeks:
        return []

    # Max CTL across all metrics (for TAPER/PEAK near-peak detection)
    max_ctl = max(m.ctl for m in load_metrics)

    # Classify each week
    classified: list[tuple[dict, str]] = []
    for i, week in enumerate(weeks):
        prev = weeks[i - 1] if i > 0 else None
        label = _classify_week(week, prev, max_ctl)
        classified.append((week, label))

    # Merge consecutive same-label weeks into blocks
    blocks: list[Block] = []
    i = 0
    while i < len(classified):
        week, label = classified[i]
        # Collect consecutive weeks with the same label
        j = i
        while j < len(classified) and classified[j][1] == label:
            j += 1
        # weeks[i:j] form one block
        block_weeks = [classified[k][0] for k in range(i, j)]
        block_start = block_weeks[0]["start_date"]
        block_end = block_weeks[-1]["end_date"]
        ctl_start = block_weeks[0]["first_ctl"]
        ctl_end = block_weeks[-1]["last_ctl"]
        n_weeks = j - i
        total_tss = sum(w["total_tss"] for w in block_weeks)
        total_days = sum(w["n_days"] for w in block_weeks)
        mean_weekly_tss = total_tss / n_weeks if n_weeks > 0 else 0.0

        evidence = (
            f"CTL {ctl_start:.1f}→{ctl_end:.1f} de {block_start} a {block_end} "
            f"({n_weeks} sem); TSS médio {mean_weekly_tss:.0f}/sem; "
            f"TSS total {total_tss:.0f} em {total_days} dias"
        )
        blocks.append(Block(
            start=block_start,
            end=block_end,
            block_type=label,
            evidence=evidence,
        ))
        i = j

    return blocks


def _percentile(values: list[float], pct: float) -> float:
    """Return the ``pct``-th percentile of *values* (linear interpolation).

    ``pct`` is in [0, 100].  Empty input returns 0.0.  Implemented locally to
    avoid a numpy dependency for this single use.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def _relative_tss_threshold(workouts: list[Any]) -> float:
    """Compute the Rule-3 TSS threshold from the workout list itself.

    ``max(p90(positive workout TSS), _RACE_TSS_SPIKE_FLOOR)``.  Only positive
    TSS values count toward the percentile so that rest/zero-TSS days do not
    deflate it.  When there is no usable TSS data the floor is returned.
    """
    tss_values = [
        float(getattr(w, "tss", None) or 0.0)
        for w in workouts
        if (getattr(w, "tss", None) or 0.0) > 0
    ]
    p90 = _percentile(tss_values, _RACE_TSS_PERCENTILE)
    return max(p90, _RACE_TSS_SPIKE_FLOOR)


def detect_races(workouts: list[Any]) -> list[Race]:
    """Detect race events from a list of workout objects.

    Parameters
    ----------
    workouts:
        List of workout-like objects.  Required attributes:
        ``workout_date`` (date), ``name`` (str), ``workout_type`` (str or
        WorkoutType), ``tss`` (float | None), ``intensity_factor`` (float | None).

    Returns
    -------
    list[Race]
        One Race per detected date (deduplication by date), sorted chronologically.
        Evidence cites the reason for classification.

    Detection rules (first match wins for evidence label; date-deduplicated)
    -----------------------------------------------------------------------
    1. workout_type == 'RACE' or WorkoutType.RACE  (primary)
    2. Name contains race keyword (case-insensitive)  (primary)
    3. (Fallback) TSS >= relative threshold AND IF >= 0.85, where the threshold
       is ``max(p90(workout_tss), 150.0)`` computed from this workout list.
    """
    seen_dates: dict[date, Race] = {}

    # Rule-3 relative threshold, self-contained from the workout list itself.
    tss_threshold = _relative_tss_threshold(workouts)

    for w in workouts:
        d = w.workout_date
        name = str(getattr(w, "name", "") or "")
        wtype = w.workout_type
        tss = getattr(w, "tss", None) or 0.0
        if_val = getattr(w, "intensity_factor", None) or 0.0

        # Normalise workout_type to its string value
        if hasattr(wtype, "value"):
            wtype_str = wtype.value
        else:
            wtype_str = str(wtype)
        if "." in wtype_str:
            wtype_str = wtype_str.rsplit(".", 1)[-1]

        evidence: str | None = None

        # Rule 1: type enum
        if wtype_str == WorkoutType.RACE.value:
            evidence = f"workout_type=RACE (tss={tss:.0f})"

        # Rule 2: keyword in name
        if evidence is None:
            name_lower = name.lower()
            for kw in _RACE_KEYWORDS:
                if kw in name_lower:
                    evidence = f"keyword:{kw} em nome='{name}' (tss={tss:.0f})"
                    break

        # Rule 3 (fallback): relative TSS spike + high IF
        if evidence is None and tss >= tss_threshold and if_val >= _RACE_IF_SPIKE:
            evidence = (
                f"tss_spike:tss={tss:.0f}>={tss_threshold:.0f} (p{_RACE_TSS_PERCENTILE} relativo), "
                f"if={if_val:.2f}>={_RACE_IF_SPIKE:.2f}"
            )

        if evidence is None:
            continue

        # Deduplicate by date (first encounter wins)
        if d not in seen_dates:
            seen_dates[d] = Race(date=d, name=name, evidence=evidence)

    return sorted(seen_dates.values(), key=lambda r: r.date)


def taper_windows(races: list[Race], load_metrics: list[Any]) -> list[TaperWindow]:
    """Reconstruct the 2–3 week pre-race load window for each race.

    Parameters
    ----------
    races:
        List of Race objects (e.g. from :func:`detect_races`).
    load_metrics:
        Chronologically ordered daily load-metric objects (same shape as
        :func:`detect_blocks`).

    Returns
    -------
    list[TaperWindow]
        One TaperWindow per race that has at least one metric in the lookback
        window.  Races without any metrics in [race_date - 21d, race_date] are
        silently skipped.

    Window span
    -----------
    For each race, look back up to TAPER_LOOKBACK_DAYS (21 days) before the
    race date.  Metrics on the race date itself are included.
    """
    if not races or not load_metrics:
        return []

    # Index metrics by date for O(1) lookup
    metric_by_date: dict[date, Any] = {m.metric_date: m for m in load_metrics}

    result: list[TaperWindow] = []

    for race in races:
        window_end = race.date
        window_start = window_end - timedelta(days=_TAPER_LOOKBACK_DAYS)

        # Collect metrics in the window [window_start, window_end]
        window_metrics = sorted(
            (m for m in load_metrics if window_start <= m.metric_date <= window_end),
            key=lambda m: m.metric_date,
        )

        if not window_metrics:
            # No data in window — skip
            continue

        first_m = window_metrics[0]
        last_m = window_metrics[-1]

        # ctl/atl/tsb on race day = last metric in window
        ctl_start = first_m.ctl
        ctl_race = last_m.ctl
        atl_race = last_m.atl
        tsb_race = last_m.tsb

        # Weekly TSS trend within the window
        week_buckets: dict[tuple[int, int], float] = {}
        for m in window_metrics:
            key = _week_key(m.metric_date)
            week_buckets[key] = week_buckets.get(key, 0.0) + m.daily_tss
        weekly_tss_trend = [
            round(week_buckets[k], 1)
            for k in sorted(week_buckets)
        ]

        ctl_delta = ctl_race - ctl_start
        ctl_delta_str = f"+{ctl_delta:.1f}" if ctl_delta >= 0 else f"{ctl_delta:.1f}"
        evidence = (
            f"CTL {ctl_start:.1f}→{ctl_race:.1f} ({ctl_delta_str}) "
            f"nos {len(window_metrics)} dias antes de {race.date}; "
            f"ATL={atl_race:.1f}, TSB={tsb_race:.1f} no dia da prova; "
            f"TSS semanal: {weekly_tss_trend}"
        )

        result.append(TaperWindow(
            race_date=race.date,
            ctl_start=ctl_start,
            ctl_race=ctl_race,
            atl_race=atl_race,
            tsb_race=tsb_race,
            weekly_tss_trend=weekly_tss_trend,
            evidence=evidence,
        ))

    return result


def coach_comment_terms(
    workouts: list[Any],
    top_n: int = 30,
) -> list[tuple[str, int]]:
    """Extract top term/phrase frequencies from coach_comments across workouts.

    Parameters
    ----------
    workouts:
        Workout-like objects.  Comments are sourced from
        ``workout.extra["coach_comments"]`` (str).  Workouts with no extra,
        no coach_comments key, or empty comment are skipped.
    top_n:
        Maximum number of (term, count) tuples to return.  Defaults to 30.

    Returns
    -------
    list[tuple[str, int]]
        Up to ``top_n`` tuples sorted by count descending.  Only terms that
        survive stopword/length filtering are included.

    Filtering
    ---------
    Tokens are normalised to lowercase and split on non-word characters.
    Excluded:
    - Tokens in _PORTUGUESE_STOPWORDS
    - Single-character tokens (unless in _CYCLING_WHITELIST)
    - Pure-digit tokens

    Cycling domain terms in _CYCLING_WHITELIST are always retained.
    """
    counter: Counter[str] = Counter()

    for w in workouts:
        extra = getattr(w, "extra", None)
        if not extra:
            continue
        comment = extra.get("coach_comments", "")
        if not comment:
            continue

        tokens = re.split(r"\W+", comment.lower())
        for token in tokens:
            if not token:
                continue
            # Skip pure digits
            if token.isdigit():
                continue
            # Keep cycling whitelist terms regardless of other rules
            if token in _CYCLING_WHITELIST:
                counter[token] += 1
                continue
            # Skip stopwords
            if token in _PORTUGUESE_STOPWORDS:
                continue
            # Skip single-character tokens not in whitelist
            if len(token) <= 1:
                continue
            counter[token] += 1

    return counter.most_common(top_n)
