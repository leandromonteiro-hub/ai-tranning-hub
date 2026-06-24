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
       PowerCurvePoint, AthleteProfile.twin_seed including data_richness) which
       also builds the markdown report ONCE and returns it in the summary.
    2. Writes docs/atletas/<slug>-perfil.md from summary["report_md"].
    3. Commits and prints a short summary (including data richness).

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
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.tenant import TenantContext
from app.models.enums import Role
from app.repositories.athlete_repo import AthleteRepository

# DB persistence + report building live in the reusable service (single source of truth)
from app.services.analysis.profile_service import generate_and_persist_profile

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
) -> str:
    """Run the full analysis pipeline for one athlete and write the report.

    Delegates ALL analysis + DB persistence to ``generate_and_persist_profile``
    (which runs the pipeline exactly once and returns the built markdown in
    ``summary["report_md"]``), then writes that markdown to
    ``output_dir/<slug>-perfil.md``.

    Parameters
    ----------
    session:      AsyncSession (caller manages commit/rollback).
    athlete_id:   UUID of the athlete.
    athlete_name: Full name (fed to the report/twin_seed).
    output_dir:   Directory where <slug>-perfil.md will be written.
    slug:         File basename slug.

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

    # --- Analysis + DB persistence + report build (single pass) ---
    summary = await generate_and_persist_profile(
        session, ctx, athlete_id, athlete_name=athlete_name
    )

    # --- Write report from the markdown the service already built ---
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{slug}-perfil.md"
    report_path.write_text(summary["report_md"], encoding="utf-8")

    # Print summary (includes richness)
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
