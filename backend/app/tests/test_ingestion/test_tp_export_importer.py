"""TDD tests for tp_export_importer — folder orchestrator (ST4).

Strategy: Build a tiny FAKE athlete folder in tmp_path with synthetic zips
(no real athlete data). Run import_athlete_folder TWICE with the same
in-memory SQLite session; assert second run creates 0 new rows.

Fixture mirrors test_anamnese.py (SQLite + StaticPool, excludes 'embeddings').
An FTP row is seeded so recompute_load_metrics can compute TSS correctly.
"""
from __future__ import annotations

import gzip
import io
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.core.tenant import TenantContext
from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role
from app.models.metrics import FtpHistory, RecoveryMetric, SubjectiveMetric
from app.models.workout import WorkoutCompleted, WorkoutPlanned

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers to build synthetic zips
# ---------------------------------------------------------------------------

def _build_metrics_csv() -> bytes:
    """Two days of HRV + Sleep metrics in long format."""
    rows = [
        {"Timestamp": "2026-01-10 06:00:00", "Type": "HRV", "Value": 55.0},
        {"Timestamp": "2026-01-10 06:00:00", "Type": "Pulse", "Value": 48.0},
        {"Timestamp": "2026-01-10 06:00:00", "Type": "Sleep Hours", "Value": 7.5},
        {"Timestamp": "2026-01-10 06:00:00", "Type": "Notes", "Value": "good sleep"},
        {"Timestamp": "2026-01-11 06:00:00", "Type": "HRV", "Value": 50.0},
        {"Timestamp": "2026-01-11 06:00:00", "Type": "Pulse", "Value": 52.0},
        {"Timestamp": "2026-01-11 06:00:00", "Type": "Sleep Hours", "Value": 6.5},
        # unmapped — should be reported but not stored
        {"Timestamp": "2026-01-11 06:00:00", "Type": "Time Awake", "Value": 20.0},
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def _build_workouts_csv() -> bytes:
    """1 completed + 1 planned + 1 Day Off in wide format."""
    rows = [
        {
            "WorkoutDay": "2026-01-10",
            "WorkoutType": "Bike",
            "Title": "Morning Ride",
            "WorkoutDescription": "Easy Z2",
            "TimeTotalInHours": 1.5,
            "TSS": 60.0,
            "IF": 0.72,
            "PowerAverage": 185.0,
            "DistanceInMeters": 40000.0,
            "HeartRateAverage": 135.0,
            "PlannedDuration": None,
        },
        {
            "WorkoutDay": "2026-01-12",
            "WorkoutType": "Bike",
            "Title": "Planned Tempo",
            "WorkoutDescription": "Sweet spot intervals",
            "TimeTotalInHours": None,
            "TSS": None,
            "IF": None,
            "PowerAverage": None,
            "DistanceInMeters": None,
            "HeartRateAverage": None,
            "PlannedDuration": 2.0,
        },
        {
            "WorkoutDay": "2026-01-13",
            "WorkoutType": "Day Off",
            "Title": None,
            "WorkoutDescription": None,
            "TimeTotalInHours": None,
            "TSS": None,
            "IF": None,
            "PowerAverage": None,
            "DistanceInMeters": None,
            "HeartRateAverage": None,
            "PlannedDuration": None,
        },
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


_MINIMAL_GPX = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test"
     xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Test Ride</name>
    <trkseg>
      <trkpt lat="48.0" lon="16.0">
        <ele>200</ele>
        <time>2026-01-11T07:00:00Z</time>
      </trkpt>
      <trkpt lat="48.001" lon="16.001">
        <ele>210</ele>
        <time>2026-01-11T08:00:00Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>"""


def _build_fake_folder(base: Path) -> None:
    """Create a fake TP-2026/ subfolder with three zips."""
    tp_dir = base / "TP-2026"
    tp_dir.mkdir()

    # MetricsExport zip
    metrics_zip = tp_dir / "MetricsExport-2026.zip"
    with zipfile.ZipFile(metrics_zip, "w") as zf:
        zf.writestr("metrics.csv", _build_metrics_csv())

    # WorkoutExport zip
    workouts_zip = tp_dir / "WorkoutExport-2026.zip"
    with zipfile.ZipFile(workouts_zip, "w") as zf:
        zf.writestr("workouts.csv", _build_workouts_csv())

    # WorkoutFileExport zip — contains one .gpx.gz
    files_zip = tp_dir / "WorkoutFileExport-2026.zip"
    gpx_gz = gzip.compress(_MINIMAL_GPX)
    with zipfile.ZipFile(files_zip, "w") as zf:
        zf.writestr("activity_20260111.gpx.gz", gpx_gz)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session():
    """In-memory SQLite async session with all tables (except embeddings)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as session:
        # Seed athlete
        athlete = Athlete(
            email="test_tp@example.com",
            hashed_password=hash_password("pw12345678"),
            full_name="Test TP",
            role=Role.ATHLETE,
            tenant_id="tp_test_tenant",
        )
        session.add(athlete)
        await session.flush()

        # Seed FTP so recompute can calculate TSS
        ftp = FtpHistory(
            athlete_id=athlete.id,
            ftp_watts=250.0,
            valid_from=date(2025, 1, 1),
            valid_to=None,
            method="manual",
            source="test",
            created_by=athlete.id,
        )
        session.add(ftp)
        await session.commit()

        yield session, athlete

    await engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_first_run_creates_rows(db_session, tmp_path):
    """First import creates workouts, metrics and planned rows."""
    from app.services.ingestion.tp_export_importer import import_athlete_folder

    session, athlete = db_session
    ctx = TenantContext(athlete_id=athlete.id, tenant_id=athlete.tenant_id, role=Role.ATHLETE)

    _build_fake_folder(tmp_path)

    report = await import_athlete_folder(session, ctx, athlete.id, tmp_path)
    await session.flush()

    # At least the CSV-completed workout was created (GPX may add one more)
    assert report.workouts_completed >= 1
    # 1 planned workout
    assert report.workouts_planned == 1
    # 1 rest day
    assert report.rest_days == 1
    # 2 recovery days (HRV data for 2026-01-10 and 2026-01-11)
    assert report.recovery_days == 2
    # 1 subjective day (Notes field for 2026-01-10)
    assert report.subjective_days == 1
    # Period populated
    assert report.period_start is not None
    assert report.period_end is not None
    assert report.period_start <= report.period_end
    # Unmapped metric type reported
    assert "Time Awake" in report.unmapped_metric_types


async def test_second_run_is_idempotent(db_session, tmp_path):
    """Running import twice on the same folder creates 0 new rows."""
    from app.services.ingestion.tp_export_importer import import_athlete_folder

    session, athlete = db_session
    ctx = TenantContext(athlete_id=athlete.id, tenant_id=athlete.tenant_id, role=Role.ATHLETE)

    _build_fake_folder(tmp_path)

    # First run
    await import_athlete_folder(session, ctx, athlete.id, tmp_path)
    await session.flush()

    # Count rows after first run
    from sqlalchemy import func, select
    wc1 = (await session.execute(
        select(func.count()).select_from(WorkoutCompleted).where(
            WorkoutCompleted.athlete_id == athlete.id,
            WorkoutCompleted.deleted_at.is_(None),
        )
    )).scalar()
    wp1 = (await session.execute(
        select(func.count()).select_from(WorkoutPlanned).where(
            WorkoutPlanned.athlete_id == athlete.id,
            WorkoutPlanned.deleted_at.is_(None),
        )
    )).scalar()
    rm1 = (await session.execute(
        select(func.count()).select_from(RecoveryMetric).where(
            RecoveryMetric.athlete_id == athlete.id,
            RecoveryMetric.deleted_at.is_(None),
        )
    )).scalar()
    sm1 = (await session.execute(
        select(func.count()).select_from(SubjectiveMetric).where(
            SubjectiveMetric.athlete_id == athlete.id,
            SubjectiveMetric.deleted_at.is_(None),
        )
    )).scalar()

    # Second run
    report2 = await import_athlete_folder(session, ctx, athlete.id, tmp_path)
    await session.flush()

    # Count rows after second run
    wc2 = (await session.execute(
        select(func.count()).select_from(WorkoutCompleted).where(
            WorkoutCompleted.athlete_id == athlete.id,
            WorkoutCompleted.deleted_at.is_(None),
        )
    )).scalar()
    wp2 = (await session.execute(
        select(func.count()).select_from(WorkoutPlanned).where(
            WorkoutPlanned.athlete_id == athlete.id,
            WorkoutPlanned.deleted_at.is_(None),
        )
    )).scalar()
    rm2 = (await session.execute(
        select(func.count()).select_from(RecoveryMetric).where(
            RecoveryMetric.athlete_id == athlete.id,
            RecoveryMetric.deleted_at.is_(None),
        )
    )).scalar()
    sm2 = (await session.execute(
        select(func.count()).select_from(SubjectiveMetric).where(
            SubjectiveMetric.athlete_id == athlete.id,
            SubjectiveMetric.deleted_at.is_(None),
        )
    )).scalar()

    assert wc2 == wc1, f"WorkoutCompleted grew: {wc1} -> {wc2}"
    assert wp2 == wp1, f"WorkoutPlanned grew: {wp1} -> {wp2}"
    assert rm2 == rm1, f"RecoveryMetric grew: {rm1} -> {rm2}"
    assert sm2 == sm1, f"SubjectiveMetric grew: {sm1} -> {sm2}"

    # Second run report should show duplicates_skipped > 0
    assert report2.duplicates_skipped >= 1


async def test_report_coverage_fields(db_session, tmp_path):
    """Report includes coverage percentages and anomalies list."""
    from app.services.ingestion.tp_export_importer import import_athlete_folder

    session, athlete = db_session
    ctx = TenantContext(athlete_id=athlete.id, tenant_id=athlete.tenant_id, role=Role.ATHLETE)

    _build_fake_folder(tmp_path)
    report = await import_athlete_folder(session, ctx, athlete.id, tmp_path)

    # Coverage fields are floats in [0, 100]
    assert 0.0 <= report.pct_power <= 100.0
    assert 0.0 <= report.pct_hr <= 100.0
    assert 0.0 <= report.pct_hrv <= 100.0
    # Anomalies is a list (may be empty for clean data)
    assert isinstance(report.anomalies, list)
