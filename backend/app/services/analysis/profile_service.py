"""Reusable profile-generation service (DB seed, no file I/O).

Extracts the DB-side analysis-and-persist orchestration from
``app.scripts.analyze_athlete`` so that BOTH the CLI and the future
onboarding endpoint can call it without writing a markdown file.

Public API
----------
generate_and_persist_profile(session, ctx, athlete_id) -> dict
    Loads athlete data, runs the full analysis pipeline, persists
    FtpHistory + PowerCurvePoint + AthleteProfile.twin_seed (idempotent),
    and returns a compact summary dict.

Loader helpers
--------------
_load_workouts_with_streams   — reused / re-exported for the CLI
_load_load_metrics            — reused / re-exported for the CLI
_load_recovery_metrics        — recovery days for richness computation
_load_profile                 — reused / re-exported for the CLI
_build_quarterly_windows      — reused / re-exported for the CLI

Persistence helpers
-------------------
_upsert_ftp_history           — idempotent FtpHistory upsert
_upsert_power_curve_points    — idempotent PowerCurvePoint upsert

Idempotency strategy
--------------------
- FtpHistory: match on (athlete_id, valid_from, source="task2_analysis");
  update ftp_watts/method/valid_to if exists, insert if not.
- PowerCurvePoint: match on (athlete_id, duration_s, period_label="all-time");
  update best_power if exists, insert if not.
- AthleteProfile.twin_seed: always overwrite (last-write-wins).
- AthleteProfile row: created if missing (freshly-registered athlete).
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.tenant import TenantContext
from app.models.athlete import AthleteProfile
from app.models.enums import Role
from app.models.metrics import FtpHistory, LoadMetric, PowerCurvePoint, RecoveryMetric
from app.models.workout import WorkoutCompleted, WorkoutStream
from app.services.analysis.data_richness import compute_richness
from app.services.analysis.ftp_estimator import all_time_power_curve, estimate_ftp_timeline
from app.services.analysis.methodology import (
    coach_comment_terms,
    detect_blocks,
    detect_races,
    taper_windows,
)
from app.services.analysis.profile_metrics import (
    best_power_marks,
    intensity_distribution,
    modality_split,
    weekly_volume_trend,
)
from app.services.analysis.report_builder import build_profile_report

# ---------------------------------------------------------------------------
# Data loading helpers (moved from analyze_athlete.py; imported there)
# ---------------------------------------------------------------------------


async def _load_workouts_with_streams(
    session: AsyncSession, athlete_id: uuid.UUID
) -> list[WorkoutCompleted]:
    """Load all non-deleted completed workouts for the athlete, eager-loading streams."""
    stmt = (
        select(WorkoutCompleted)
        .where(
            WorkoutCompleted.athlete_id == athlete_id,
            WorkoutCompleted.deleted_at.is_(None),
        )
        .options(selectinload(WorkoutCompleted.streams))
        .order_by(WorkoutCompleted.workout_date)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def _load_load_metrics(
    session: AsyncSession, athlete_id: uuid.UUID
) -> list[LoadMetric]:
    """Load all non-deleted load metrics for the athlete, ordered by date."""
    stmt = (
        select(LoadMetric)
        .where(
            LoadMetric.athlete_id == athlete_id,
            LoadMetric.deleted_at.is_(None),
        )
        .order_by(LoadMetric.metric_date)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def _load_recovery_metrics(
    session: AsyncSession, athlete_id: uuid.UUID
) -> list[RecoveryMetric]:
    """Load all non-deleted recovery metrics for the athlete, ordered by date."""
    stmt = (
        select(RecoveryMetric)
        .where(
            RecoveryMetric.athlete_id == athlete_id,
            RecoveryMetric.deleted_at.is_(None),
        )
        .order_by(RecoveryMetric.metric_date)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def _load_profile(
    session: AsyncSession, athlete_id: uuid.UUID
) -> AthleteProfile | None:
    """Load the athlete's profile (or None if not yet created)."""
    stmt = select(AthleteProfile).where(
        AthleteProfile.athlete_id == athlete_id,
        AthleteProfile.deleted_at.is_(None),
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Window helpers for FTP timeline (moved from analyze_athlete.py)
# ---------------------------------------------------------------------------


def _build_quarterly_windows(
    workouts: list[WorkoutCompleted],
) -> list[tuple[date, date | None, list[list[float]]]]:
    """Build quarterly FTP estimation windows from workout history.

    For each 90-day window from the first workout date to today, collect the
    power streams. Windows with no streams are included (estimate_ftp_timeline
    will skip them silently).
    """
    if not workouts:
        return []

    first_date = workouts[0].workout_date
    last_date = workouts[-1].workout_date

    # Build quarterly windows (90 days each)
    windows: list[tuple[date, date | None, list[list[float]]]] = []
    window_start = date(first_date.year, ((first_date.month - 1) // 3) * 3 + 1, 1)

    while window_start <= last_date:
        # Quarter end = start + ~90 days (3 months, approximate)
        quarter_month_end = window_start.month + 2
        quarter_year_end = window_start.year
        if quarter_month_end > 12:
            quarter_month_end -= 12
            quarter_year_end += 1
        # Last day of the quarter
        # Get first day of next quarter, then subtract one day
        next_q_month = quarter_month_end + 1
        next_q_year = quarter_year_end
        if next_q_month > 12:
            next_q_month = 1
            next_q_year += 1
        window_end = date(next_q_year, next_q_month, 1) - timedelta(days=1)

        # Is this the last (or only) window?
        is_last = window_end >= last_date
        valid_to = None if is_last else window_end

        # Collect streams for workouts in [window_start, window_end]
        streams_in_window: list[list[float]] = []
        for w in workouts:
            if window_start <= w.workout_date <= window_end:
                for stream in w.streams:
                    if stream.power:
                        streams_in_window.append(list(stream.power))

        windows.append((window_start, valid_to, streams_in_window))

        # Advance to next quarter
        next_start_month = window_start.month + 3
        next_start_year = window_start.year
        if next_start_month > 12:
            next_start_month -= 12
            next_start_year += 1
        window_start = date(next_start_year, next_start_month, 1)

    return windows


# ---------------------------------------------------------------------------
# Idempotent persistence helpers (moved from analyze_athlete.py)
# ---------------------------------------------------------------------------


async def _upsert_ftp_history(
    session: AsyncSession,
    athlete_id: uuid.UUID,
    ctx: TenantContext,
    ftp_estimates: list[Any],
) -> int:
    """Upsert FtpHistory rows idempotently.

    Match on (athlete_id, valid_from, source="task2_analysis").
    Update ftp_watts/method/valid_to if exists; insert otherwise.
    Returns count of rows inserted or updated.
    """
    count = 0
    for est in ftp_estimates:
        stmt = select(FtpHistory).where(
            FtpHistory.athlete_id == athlete_id,
            FtpHistory.valid_from == est.valid_from,
            FtpHistory.source == "task2_analysis",
            FtpHistory.deleted_at.is_(None),
        )
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.ftp_watts = est.ftp_watts
            existing.method = est.method
            existing.valid_to = est.valid_to
        else:
            row = FtpHistory(
                athlete_id=athlete_id,
                ftp_watts=est.ftp_watts,
                valid_from=est.valid_from,
                valid_to=est.valid_to,
                method=est.method,
                source="task2_analysis",
            )
            row.created_by = ctx.athlete_id
            session.add(row)
        count += 1

    await session.flush()
    return count


async def _upsert_power_curve_points(
    session: AsyncSession,
    athlete_id: uuid.UUID,
    ctx: TenantContext,
    power_curve_dict: dict[int, float],
) -> int:
    """Upsert PowerCurvePoint rows idempotently.

    Match on (athlete_id, duration_s, period_label="all-time").
    Update best_power if exists; insert otherwise.
    Returns count of rows inserted or updated.
    """
    count = 0
    for duration_s, watts in power_curve_dict.items():
        stmt = select(PowerCurvePoint).where(
            PowerCurvePoint.athlete_id == athlete_id,
            PowerCurvePoint.duration_s == duration_s,
            PowerCurvePoint.period_label == "all-time",
            PowerCurvePoint.deleted_at.is_(None),
        )
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.best_power = watts
        else:
            row = PowerCurvePoint(
                athlete_id=athlete_id,
                duration_s=duration_s,
                best_power=watts,
                period_label="all-time",
            )
            row.created_by = ctx.athlete_id
            session.add(row)
        count += 1

    await session.flush()
    return count


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_and_persist_profile(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    athlete_name: str = "Athlete",
) -> dict:
    """Run the full analysis pipeline and persist results for one athlete.

    This function is the DB-persistence core of Task 2. It does NOT write any
    files (markdown or otherwise) — but it DOES build the markdown report once
    and return it in the summary so the CLI can write it without re-running the
    pipeline. The future onboarding endpoint can simply ignore ``report_md``.

    Parameters
    ----------
    session:
        AsyncSession — caller manages commit/rollback.
    ctx:
        TenantContext for the athlete (used for created_by on new rows and for
        multi-tenant isolation). ``ctx.athlete_id`` is used as ``created_by``.
    athlete_id:
        UUID of the athlete to analyse.
    athlete_name:
        Display name fed to report_builder/twin_seed. Defaults to "Athlete"
        (the onboarding endpoint can rely on the default).

    Returns
    -------
    dict with keys:
        n_workouts      : int   — total workouts analysed
        weeks           : int   — weeks covered by the history
        ftp_recent      : float | None — most recent FTP estimate in watts
        n_blocks        : int   — training blocks detected
        n_races         : int   — race events detected
        excluded_power_streams : int — streams excluded as implausible
        richness        : dict  — RichnessIndex as a plain dict
        report_md       : str   — the built PT-BR markdown report
    """
    # --- Load data ---
    workouts = await _load_workouts_with_streams(session, athlete_id)
    load_metrics = await _load_load_metrics(session, athlete_id)
    recovery_metrics = await _load_recovery_metrics(session, athlete_id)
    profile = await _load_profile(session, athlete_id)

    # Weight from profile if available
    weight_kg: float | None = profile.weight_kg if profile is not None else None

    # --- ST2.1: FTP estimation + power curve ---
    all_streams = [
        list(stream.power)
        for w in workouts
        for stream in w.streams
        if stream.power
    ]
    power_curve_dict, excluded_streams = all_time_power_curve(all_streams)

    windows = _build_quarterly_windows(workouts)
    ftp_timeline = estimate_ftp_timeline(windows)

    # --- ST2.2: Profile metrics ---
    vol_trend = weekly_volume_trend(workouts)
    modality = modality_split(workouts)
    intensity = intensity_distribution(workouts)
    marks = best_power_marks(power_curve_dict, weight_kg=weight_kg)

    # --- ST2.3: Methodology ---
    blocks = detect_blocks(load_metrics)
    races = detect_races(workouts)
    tapers = taper_windows(races, load_metrics)
    comment_terms = coach_comment_terms(workouts)

    # --- Report builder (builds the markdown report + twin_seed in one pass) ---
    report_md, twin_seed = build_profile_report(
        athlete_name=athlete_name,
        weight_kg=weight_kg,
        volume_trend=vol_trend,
        modality=modality,
        intensity=intensity,
        power_marks=marks,
        blocks=blocks,
        races=races,
        tapers=tapers,
        comment_terms=comment_terms,
        ftp_timeline=ftp_timeline,
        excluded_streams=excluded_streams,
    )

    # --- Data richness (T4.1) ---
    period_start = workouts[0].workout_date if workouts else None
    period_end = workouts[-1].workout_date if workouts else None
    richness = compute_richness(
        workouts=workouts,
        recovery_days=recovery_metrics,
        period_start=period_start,
        period_end=period_end,
    )
    twin_seed["data_richness"] = asdict(richness)

    # --- Persist FtpHistory (idempotent) ---
    ftp_count = 0
    if ftp_timeline:
        ftp_count = await _upsert_ftp_history(session, athlete_id, ctx, ftp_timeline)

    # --- Persist PowerCurvePoint (idempotent) ---
    pc_count = 0
    if power_curve_dict:
        pc_count = await _upsert_power_curve_points(session, athlete_id, ctx, power_curve_dict)

    # --- Persist twin_seed on AthleteProfile (create if missing) ---
    if profile is None:
        # Freshly-registered athlete: create a minimal profile row
        profile = AthleteProfile(athlete_id=athlete_id)
        profile.created_by = ctx.athlete_id
        session.add(profile)

    profile.twin_seed = twin_seed
    session.add(profile)
    await session.flush()

    # --- Build summary dict ---
    weeks = (
        vol_trend.trend.weeks_analysed
        if vol_trend.trend
        else len(vol_trend.weeks)
    )
    ftp_recent = ftp_timeline[-1].ftp_watts if ftp_timeline else None

    return {
        "n_workouts": len(workouts),
        "weeks": weeks,
        "ftp_recent": ftp_recent,
        "n_blocks": len(blocks),
        "n_races": len(races),
        "excluded_power_streams": excluded_streams,
        "richness": asdict(richness),
        "report_md": report_md,
    }
