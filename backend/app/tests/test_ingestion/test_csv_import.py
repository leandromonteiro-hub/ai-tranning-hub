"""CSV parsing + full import pipeline (dedup, metrics, persistence)."""
from __future__ import annotations

import io
from datetime import date, datetime

import pandas as pd
import pytest

from app.models.enums import ImportStatus
from app.models.metrics import FtpHistory
from app.repositories.metrics_repo import LoadMetricRepository
from app.repositories.workout_repo import WorkoutRepository
from app.services.ingestion import csv_importer
from app.services.ingestion.ingestion_service import import_file
from app.services.metrics.recompute import recompute_load_metrics
from app.tests.conftest import ctx_for


def _sample_csv() -> bytes:
    df = pd.DataFrame(
        [
            {
                "WorkoutDay": datetime(2026, 1, 1, 7, 0).isoformat(),
                "Title": "Endurance",
                "TimeTotalInHours": 2.0,
                "TSS": 110,
                "IF": 0.72,
                "NormalizedPower": 205,
                "AverageHeartRate": 142,
            },
            {
                "WorkoutDay": datetime(2026, 1, 3, 7, 0).isoformat(),
                "Title": "Threshold",
                "TimeTotalInHours": 1.0,
                "TSS": 95,
                "IF": 0.95,
                "NormalizedPower": 270,
                "AverageHeartRate": 165,
            },
        ]
    )
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def test_parse_csv_extracts_activities():
    acts = csv_importer.parse_csv(_sample_csv())
    assert len(acts) == 2
    assert acts[0].duration_s == 7200
    assert acts[0].source_tss == 110
    assert acts[1].source_if == 0.95


@pytest.mark.asyncio
async def test_import_persists_workouts_and_dedupes(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    data = _sample_csv()

    result = await import_file(session, ctx, a.id, "tp.csv", data, source="trainingpeaks")
    await session.flush()
    assert result.imported_file.status == ImportStatus.COMPLETED
    assert result.workouts_created == 2

    workouts = await WorkoutRepository(session, ctx).list()
    assert len(workouts) == 2

    # Re-importing identical bytes is detected as a duplicate (content hash).
    dup = await import_file(session, ctx, a.id, "tp.csv", data, source="trainingpeaks")
    assert dup.imported_file.status == ImportStatus.DUPLICATE
    assert dup.duplicates_skipped == 1
    assert len(await WorkoutRepository(session, ctx).list()) == 2


@pytest.mark.asyncio
async def test_import_then_recompute_load_series(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    session.add(
        FtpHistory(athlete_id=a.id, ftp_watts=250, valid_from=date(2025, 1, 1))
    )
    await session.flush()

    await import_file(session, ctx, a.id, "tp.csv", _sample_csv(), source="tp")
    days = await recompute_load_metrics(session, ctx, a.id)
    await session.flush()
    assert days > 0

    load = await LoadMetricRepository(session, ctx).latest()
    assert load is not None
    assert load.ctl > 0
