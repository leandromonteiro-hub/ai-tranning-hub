"""CLI: ingest a TrainingPeaks export folder for a named athlete.

Usage (inside the container):
    python -m app.scripts.import_athlete --athlete <slug> --email <email>

Where:
    --athlete  slug name that matches a subfolder under docs/data-atletas/
               e.g. "leandromonteiro" → docs/data-atletas/leandromonteiro/
    --email    athlete's email address (used to resolve their DB record)

The script builds a TenantContext, calls import_athlete_folder, commits the
session, and prints the ingestion report as readable text + a JSON block.

Mirror of app.scripts.sample_import session/ctx setup.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
from pathlib import Path

from app.core.database import AsyncSessionLocal
from app.core.tenant import TenantContext
from app.models.enums import Role
from app.repositories.athlete_repo import AthleteRepository
from app.services.ingestion.tp_export_importer import IngestionReport, import_athlete_folder

# Folder where real athlete data lives (gitignored). In a host checkout the file
# is at <repo>/backend/app/scripts/import_athlete.py, so the repo root is
# parents[3]. Inside the container the code lives at /app and the data is mounted
# elsewhere, so allow an explicit override via DATA_ATLETAS_DIR.
_DATA_ROOT = Path(
    os.environ.get(
        "DATA_ATLETAS_DIR",
        Path(__file__).resolve().parents[3] / "docs" / "data-atletas",
    )
)


def _print_report(report: IngestionReport) -> None:
    """Print a human-readable summary and a JSON block."""
    print("\n" + "=" * 60)
    print("  TrainingPeaks Ingestion Report")
    print("=" * 60)

    period = (
        f"{report.period_start} → {report.period_end}"
        if report.period_start
        else "N/A"
    )
    print(f"  Period:              {period}")
    print(f"  Workouts completed:  {report.workouts_completed}")
    print(f"  Workouts planned:    {report.workouts_planned}")
    print(f"  Rest days:           {report.rest_days}")
    print(f"  Recovery days:       {report.recovery_days}")
    print(f"  Subjective days:     {report.subjective_days}")
    print(f"  Duplicates skipped:  {report.duplicates_skipped}")
    print()
    print(f"  Power coverage:      {report.pct_power:.1f}%")
    print(f"  HR coverage:         {report.pct_hr:.1f}%")
    print(f"  HRV coverage:        {report.pct_hrv:.1f}%")

    if report.unmapped_metric_types:
        print("\n  Unmapped metric types:")
        for t, n in report.unmapped_metric_types.items():
            print(f"    {t}: {n}")

    if report.anomalies:
        print(f"\n  Anomalies ({len(report.anomalies)}):")
        for a in report.anomalies[:20]:
            print(f"    ⚠  {a}")
        if len(report.anomalies) > 20:
            print(f"    ... and {len(report.anomalies) - 20} more")

    print("\n" + "=" * 60)
    print("  JSON:")
    print("=" * 60)

    d = dataclasses.asdict(report)
    # Make date objects JSON-serialisable
    for k in ("period_start", "period_end"):
        if d[k] is not None:
            d[k] = str(d[k])
    print(json.dumps(d, indent=2, default=str))
    print("=" * 60 + "\n")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import a TrainingPeaks export folder for an athlete."
    )
    parser.add_argument(
        "--athlete",
        required=True,
        help="Athlete slug (subfolder name under docs/data-atletas/)",
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Athlete email address (to resolve their DB record)",
    )
    args = parser.parse_args()

    folder = _DATA_ROOT / args.athlete
    if not folder.exists():
        print(f"ERROR: folder not found: {folder}")
        raise SystemExit(1)

    async with AsyncSessionLocal() as session:
        athlete = await AthleteRepository(session).get_by_email(args.email)
        if not athlete:
            print(
                f"ERROR: no athlete with email '{args.email}' found. "
                "Run `make seed` or create the athlete first."
            )
            raise SystemExit(1)

        ctx = TenantContext(
            athlete_id=athlete.id,
            tenant_id=athlete.tenant_id,
            role=Role.ATHLETE,
        )

        print(f"Importing folder: {folder}")
        print(f"Athlete:          {athlete.full_name} <{athlete.email}> (id={athlete.id})")

        report = await import_athlete_folder(session, ctx, athlete.id, folder)
        await session.commit()

    _print_report(report)


if __name__ == "__main__":
    asyncio.run(main())
