"""CLI: run full athlete profile analysis and persist results.

Usage (inside the container):
    python -m app.scripts.analyze_athlete --email <email> [--slug <slug>]

Arguments:
    --email   Athlete email address (resolves DB record).
    --slug    Output filename slug (default: derived from email prefix).

Environment overrides:
    PROFILE_OUT_DIR  Directory for output markdown files.
                     Default: <repo_root>/docs/atletas

What it does:
    1. Loads the athlete's workouts (+ power streams), load_metrics, profile.
    2. Runs ST2.1 (FTP estimation + power curve), ST2.2 (profile metrics),
       ST2.3 (methodology detection), and report_builder.
    3. Writes docs/atletas/<slug>-perfil.md.
    4. Persists FtpHistory rows (idempotent via source="task2_analysis" +
       valid_from), PowerCurvePoint rows (idempotent via period_label="all-time"),
       and AthleteProfile.twin_seed.
    5. Commits and prints a short summary.

Idempotency strategy:
    - FtpHistory: match on (athlete_id, valid_from, source="task2_analysis");
      update ftp_watts/method/valid_to if exists, insert if not.
    - PowerCurvePoint: match on (athlete_id, duration_s, period_label="all-time");
      update best_power if exists, insert if not.
    - AthleteProfile.twin_seed: always overwrite (last-write-wins).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.core.tenant import TenantContext
from app.models.athlete import Athlete, AthleteProfile
from app.models.enums import Role
from app.models.metrics import FtpHistory, LoadMetric, PowerCurvePoint
from app.models.workout import WorkoutCompleted, WorkoutStream
from app.repositories.athlete_repo import AthleteRepository
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
# Paths
# ---------------------------------------------------------------------------

_PROFILE_OUT_DIR = Path(
    os.environ.get(
        "PROFILE_OUT_DIR",
        Path(__file__).resolve().parents[3] / "docs" / "atletas",
    )
)

# ---------------------------------------------------------------------------
# Data loading helpers
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
# Window helpers for FTP timeline
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
# Idempotent persistence helpers
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
# Core analysis runner (pure DB-aware orchestration)
# ---------------------------------------------------------------------------


async def run_analysis(
    session: AsyncSession,
    athlete_id: uuid.UUID,
    athlete_name: str,
    output_dir: Path,
    slug: str,
    weight_kg: float | None = None,
) -> str:
    """Run the full analysis pipeline for one athlete.

    If weight_kg is not supplied, it will be loaded from the athlete's profile.

    Parameters
    ----------
    session:      AsyncSession (caller manages commit/rollback).
    athlete_id:   UUID of the athlete.
    athlete_name: Full name (used in report).
    output_dir:   Directory where <slug>-perfil.md will be written.
    slug:         File basename slug.
    weight_kg:    Optional weight override; loaded from profile if None.

    Returns
    -------
    str
        Absolute path to the written report file.
    """
    ctx = TenantContext(
        athlete_id=athlete_id,
        tenant_id=str(athlete_id),
        role=Role.ATHLETE,
    )

    # --- Load data ---
    workouts = await _load_workouts_with_streams(session, athlete_id)
    load_metrics = await _load_load_metrics(session, athlete_id)
    profile = await _load_profile(session, athlete_id)

    # Weight from profile if not explicitly passed
    if weight_kg is None and profile is not None:
        weight_kg = profile.weight_kg

    # --- ST2.1: FTP estimation + power curve ---
    all_streams = [
        list(stream.power)
        for w in workouts
        for stream in w.streams
        if stream.power
    ]
    power_curve_dict = all_time_power_curve(all_streams)

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

    # --- Report builder ---
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
    )

    # --- Write report ---
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{slug}-perfil.md"
    report_path.write_text(report_md, encoding="utf-8")

    # --- Persist FtpHistory (idempotent) ---
    ftp_count = 0
    if ftp_timeline:
        ftp_count = await _upsert_ftp_history(session, athlete_id, ctx, ftp_timeline)

    # --- Persist PowerCurvePoint (idempotent) ---
    pc_count = 0
    if power_curve_dict:
        pc_count = await _upsert_power_curve_points(session, athlete_id, ctx, power_curve_dict)

    # --- Persist twin_seed on AthleteProfile ---
    if profile is not None:
        profile.twin_seed = twin_seed
        session.add(profile)
        await session.flush()

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Análise concluída: {athlete_name}")
    print(f"{'='*60}")
    print(f"  Treinos analisados:      {len(workouts)}")
    print(f"  Semanas:                 {vol_trend.trend.weeks_analysed if vol_trend.trend else len(vol_trend.weeks)}")
    print(f"  FTP estimado (recente):  {ftp_timeline[-1].ftp_watts:.0f} W" if ftp_timeline else "  FTP: sem dados")
    print(f"  Blocos detectados:       {len(blocks)}")
    print(f"  Provas detectadas:       {len(races)}")
    print(f"  FtpHistory persistidos:  {ftp_count}")
    print(f"  PowerCurvePoints:        {pc_count}")
    print(f"  Relatório:               {report_path}")
    print(f"{'='*60}\n")

    return str(report_path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run athlete profile analysis and persist results."
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Athlete email address (to resolve their DB record)",
    )
    parser.add_argument(
        "--slug",
        default=None,
        help="Output filename slug (default: derived from email prefix)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Override output directory for the markdown report",
    )
    args = parser.parse_args()

    slug = args.slug or args.email.split("@")[0].replace(".", "-").replace("_", "-")
    output_dir = Path(args.out_dir) if args.out_dir else _PROFILE_OUT_DIR

    async with AsyncSessionLocal() as session:
        athlete = await AthleteRepository(session).get_by_email(args.email)
        if not athlete:
            print(f"ERROR: no athlete with email '{args.email}' found.")
            raise SystemExit(1)

        print(f"Athlete: {athlete.full_name} <{athlete.email}> (id={athlete.id})")

        await run_analysis(
            session=session,
            athlete_id=athlete.id,
            athlete_name=athlete.full_name,
            output_dir=output_dir,
            slug=slug,
        )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
