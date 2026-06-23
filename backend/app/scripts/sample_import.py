"""Generate a small synthetic TrainingPeaks-style CSV and import it for athlete1.

Demonstrates the full pipeline end-to-end (parse -> dedup -> metrics -> load
series). Run with `make import`.
"""
from __future__ import annotations

import asyncio
import io
from datetime import date, datetime, timedelta

import pandas as pd

from app.core.database import AsyncSessionLocal
from app.core.tenant import TenantContext
from app.models.enums import Role
from app.repositories.athlete_repo import AthleteRepository
from app.services.ingestion.ingestion_service import import_file
from app.services.metrics.recompute import recompute_load_metrics


def _make_csv() -> bytes:
    rows = []
    start = date.today() - timedelta(days=28)
    for i in range(28):
        d = start + timedelta(days=i)
        # Rest every 4th day.
        if i % 4 == 3:
            continue
        rows.append(
            {
                "WorkoutDay": datetime(d.year, d.month, d.day, 7, 0).isoformat(),
                "Title": f"Ride {i+1}",
                "TimeTotalInHours": 1.5 + (i % 3) * 0.5,
                "DistanceInMeters": 40000 + (i % 5) * 5000,
                "TSS": 60 + (i % 4) * 25,
                "IF": 0.72 + (i % 4) * 0.06,
                "NormalizedPower": 200 + (i % 4) * 20,
                "AverageHeartRate": 140 + (i % 3) * 8,
            }
        )
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


async def main() -> None:
    async with AsyncSessionLocal() as session:
        athlete = await AthleteRepository(session).get_by_email("athlete1@athletehub.example.com")
        if not athlete:
            print("Run `make seed` first.")
            return
        ctx = TenantContext(
            athlete_id=athlete.id, tenant_id=athlete.tenant_id, role=Role.ATHLETE
        )
        result = await import_file(
            session, ctx, athlete.id, "sample_trainingpeaks.csv", _make_csv(), source="demo"
        )
        days = await recompute_load_metrics(session, ctx, athlete.id)
        await session.commit()
        print(
            f"Imported {result.workouts_created} workouts "
            f"({result.duplicates_skipped} dupes); wrote {days} load-metric days."
        )


if __name__ == "__main__":
    asyncio.run(main())
