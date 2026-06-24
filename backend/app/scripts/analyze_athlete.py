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
    1. Calls generate_and_persist_profile (DB persistence — FtpHistory,
       PowerCurvePoint, AthleteProfile.twin_seed including data_richness).
    2. Re-runs the analysis steps to build the markdown report (no extra
       DB round-trip for workouts/profile; reads result from service).
    3. Writes docs/atletas/<slug>-perfil.md.
    4. Commits and prints a short summary.

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

# Import reusable helpers + service from profile_service (single source of truth)
from app.services.analysis.profile_service import (
    _build_quarterly_windows,
    _load_load_metrics,
    _load_profile,
    _load_workouts_with_streams,
    _upsert_ftp_history,
    _upsert_power_curve_points,
    generate_and_persist_profile,
)
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
# Core analysis runner (wraps the service + adds markdown file write)
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

    Delegates DB persistence to ``generate_and_persist_profile``, then
    re-runs the analysis to produce the markdown report and writes it to
    ``output_dir/<slug>-perfil.md``.

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

    # --- DB persistence via reusable service ---
    summary = await generate_and_persist_profile(session, ctx, athlete_id)

    # --- Reload data to build the markdown report (needs athlete_name + weight_kg) ---
    workouts = await _load_workouts_with_streams(session, athlete_id)
    load_metrics = await _load_load_metrics(session, athlete_id)
    profile = await _load_profile(session, athlete_id)

    # Weight resolution: explicit arg > profile > None
    if weight_kg is None and profile is not None:
        weight_kg = profile.weight_kg

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

    # --- Report builder ---
    report_md, _twin_seed = build_profile_report(
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

    # --- Write report ---
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{slug}-perfil.md"
    report_path.write_text(report_md, encoding="utf-8")

    # Print summary (now includes richness)
    richness = summary.get("richness", {})
    print(f"\n{'='*60}")
    print(f"  Análise concluída: {athlete_name}")
    print(f"{'='*60}")
    print(f"  Treinos analisados:      {summary['n_workouts']}")
    print(f"  Semanas:                 {summary['weeks']}")
    ftp_str = f"  FTP estimado (recente):  {summary['ftp_recent']:.0f} W" if summary["ftp_recent"] else "  FTP: sem dados"
    print(ftp_str)
    print(f"  Blocos detectados:       {summary['n_blocks']}")
    print(f"  Provas detectadas:       {summary['n_races']}")
    print(f"  Streams de potência implausíveis excluídos: {summary['excluded_power_streams']}")
    print(f"  Riqueza dos dados:       {richness.get('label', '?')} (score={richness.get('score', 0):.2f})")
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
