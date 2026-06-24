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
            # Cross-source twin of the GPX raw file (2026-01-11, ~1h = 3600s).
            # On the first run the raw file is imported first and this summary is
            # cross-deduped; a re-run must keep it deduped (idempotency).
            "WorkoutDay": "2026-01-11",
            "WorkoutType": "Bike",
            "Title": "Same Session Summary",
            "WorkoutDescription": "Z2 (also has a raw .gpx)",
            "TimeTotalInHours": 1.0,
            "TSS": 50.0,
            "IF": 0.70,
            "PowerAverage": 180.0,
            "DistanceInMeters": 31000.0,
            "HeartRateAverage": 130.0,
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


# ---------------------------------------------------------------------------
# Dedup behaviour (highest-value tests)
# ---------------------------------------------------------------------------

def _one_completed_csv(
    workout_day: str,
    distance_m,
    duration_h: float,
    title=None,
    tss: float = 55.0,
    coach_comments=None,
    pwr_zone2_min=None,
) -> bytes:
    """A workouts.csv with a single completed Bike row.

    ``title`` defaults to None so that, with no distance, the natural-key
    distance discriminator falls back to an empty name — matching a raw
    activity file that carries no name (so the same session dedups).
    Optional ``coach_comments`` / ``pwr_zone2_min`` populate the rich summary
    fields used to verify cross-source MERGE.
    """
    row = {
        "WorkoutDay": workout_day,
        "WorkoutType": "Bike",
        "Title": title,
        "WorkoutDescription": "csv summary",
        "TimeTotalInHours": duration_h,
        "TSS": tss,
        "IF": 0.7,
        "PowerAverage": 180.0,
        "DistanceInMeters": distance_m,
        "HeartRateAverage": 130.0,
        "PlannedDuration": None,
    }
    if coach_comments is not None:
        row["CoachComments"] = coach_comments
    if pwr_zone2_min is not None:
        row["PWRZone2Minutes"] = pwr_zone2_min
    df = pd.DataFrame([row])
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


# TCX with HR → import_file creates a WorkoutStream (proves the merge keeps the
# raw row's stream). TCX carries no distance, so the natural keys fall back to
# name; the CSV row uses a DIFFERENT title, so only the duration-only
# cross-source key can match — proving cross-source matching is distance/name
# independent.
_TCX_WITH_HR = b"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Biking">
      <Lap>
        <Track>
          <Trackpoint>
            <Time>2026-01-11T07:00:00Z</Time>
            <HeartRateBpm><Value>120</Value></HeartRateBpm>
            <AltitudeMeters>200</AltitudeMeters>
          </Trackpoint>
          <Trackpoint>
            <Time>2026-01-11T08:00:00Z</Time>
            <HeartRateBpm><Value>140</Value></HeartRateBpm>
            <AltitudeMeters>210</AltitudeMeters>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>"""


async def _run_cross_source_merge(session, athlete, tmp_path):
    """Build a folder where a raw TCX (HR → stream) and a workouts.csv row
    describe the SAME session (same date+duration). The CSV carries
    TSS/zone/comment fields and a DIFFERENT title; only the duration-only
    cross-source key can match. Run the importer and return the report."""
    from app.services.ingestion.tcx_importer import parse_tcx
    from app.services.ingestion.tp_export_importer import import_athlete_folder

    ctx = TenantContext(athlete_id=athlete.id, tenant_id=athlete.tenant_id, role=Role.ATHLETE)

    act = parse_tcx(_TCX_WITH_HR)[0]
    raw_date = act.started_at.strftime("%Y-%m-%d")   # 2026-01-11
    raw_duration_h = act.duration_s / 3600.0         # 3600 s → 1.0 h

    tp_dir = tmp_path / "TP-2026"
    if not tp_dir.exists():
        tp_dir.mkdir()
    with zipfile.ZipFile(tp_dir / "WorkoutExport-2026.zip", "w") as zf:
        zf.writestr(
            "workouts.csv",
            _one_completed_csv(
                raw_date, 31000.0, raw_duration_h, title="CSV Summary Title",
                tss=88.0, coach_comments="Z2 endurance", pwr_zone2_min=42.0,
            ),
        )
    with zipfile.ZipFile(tp_dir / "WorkoutFileExport-2026.zip", "w") as zf:
        zf.writestr("activity_20260111.tcx.gz", gzip.compress(_TCX_WITH_HR))

    return await import_athlete_folder(session, ctx, athlete.id, tmp_path)


async def test_cross_source_merges_csv_summary_into_raw(db_session, tmp_path):
    """A raw GPX + a workouts.csv row for the SAME session → ONE WorkoutCompleted
    (the raw one, with its stream), ENRICHED with the CSV's TSS / zone minutes /
    coach comments. Cross-source matching is duration-only (distance differs)."""
    from app.models.workout import WorkoutStream
    from sqlalchemy import func, select

    session, athlete = db_session

    report = await _run_cross_source_merge(session, athlete, tmp_path)
    await session.flush()

    # Exactly ONE completed workout despite the distance mismatch.
    rows = (await session.execute(
        select(WorkoutCompleted).where(
            WorkoutCompleted.athlete_id == athlete.id,
            WorkoutCompleted.deleted_at.is_(None),
        )
    )).scalars().all()
    assert len(rows) == 1, f"expected 1 workout (cross-source merge), got {len(rows)}"

    w = rows[0]
    # It is the raw-file one (has its stream + source_file_id).
    assert w.source_file_id is not None, "surviving row is not the raw-file workout"
    stream_count = (await session.execute(
        select(func.count()).select_from(WorkoutStream).where(
            WorkoutStream.workout_id == w.id,
        )
    )).scalar()
    assert stream_count >= 1, "merged row lost its raw stream"

    # Enriched with the CSV summary fields (raw GPX had none of these).
    assert w.tss == pytest.approx(88.0), f"TSS not merged: {w.tss}"
    assert w.extra is not None
    assert w.extra.get("coach_comments") == "Z2 endurance"
    pwr = w.extra.get("pwr_zone_minutes")
    assert pwr is not None and pwr[1] == pytest.approx(42.0), f"zone minutes not merged: {pwr}"

    # Report: one merge, zero new CSV-completed inserts for that session.
    assert report.merged_from_csv == 1


async def test_cross_source_merge_is_idempotent(db_session, tmp_path):
    """A second import keeps ONE row and does not clobber the merged values."""
    from sqlalchemy import func, select

    session, athlete = db_session

    # First run: GPX raw + CSV summary → merged into one enriched row.
    await _run_cross_source_merge(session, athlete, tmp_path)
    await session.flush()

    count1 = (await session.execute(
        select(func.count()).select_from(WorkoutCompleted).where(
            WorkoutCompleted.athlete_id == athlete.id,
            WorkoutCompleted.deleted_at.is_(None),
        )
    )).scalar()
    w1 = (await session.execute(
        select(WorkoutCompleted).where(
            WorkoutCompleted.athlete_id == athlete.id,
            WorkoutCompleted.deleted_at.is_(None),
        )
    )).scalars().one()
    tss1, coach1 = w1.tss, w1.extra.get("coach_comments")

    # Second run on the same folder.
    report2 = await _run_cross_source_merge(session, athlete, tmp_path)
    await session.flush()

    count2 = (await session.execute(
        select(func.count()).select_from(WorkoutCompleted).where(
            WorkoutCompleted.athlete_id == athlete.id,
            WorkoutCompleted.deleted_at.is_(None),
        )
    )).scalar()
    w2 = (await session.execute(
        select(WorkoutCompleted).where(
            WorkoutCompleted.athlete_id == athlete.id,
            WorkoutCompleted.deleted_at.is_(None),
        )
    )).scalars().one()

    assert count2 == count1 == 1, f"row count changed: {count1} -> {count2}"
    # Merged values unchanged (fill-if-missing never clobbers).
    assert w2.tss == pytest.approx(tss1)
    assert w2.extra.get("coach_comments") == coach1
    # The re-run re-merges (idempotent), so it is counted as a merge again.
    assert report2.merged_from_csv == 1


def _tcx_with_hr(hr1: int, hr2: int) -> bytes:
    """A TCX (2026-01-11, 07:00→08:00 = 3600 s) with HR → produces a stream.
    Distinct HR values give distinct bytes so content-hash dedup keeps both."""
    return (
        b"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Biking">
      <Lap>
        <Track>
          <Trackpoint>
            <Time>2026-01-11T07:00:00Z</Time>
            <HeartRateBpm><Value>""" + str(hr1).encode() + b"""</Value></HeartRateBpm>
            <AltitudeMeters>200</AltitudeMeters>
          </Trackpoint>
          <Trackpoint>
            <Time>2026-01-11T08:00:00Z</Time>
            <HeartRateBpm><Value>""" + str(hr2).encode() + b"""</Value></HeartRateBpm>
            <AltitudeMeters>210</AltitudeMeters>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>"""
    )


def _two_completed_csv_same_bucket() -> bytes:
    """Two completed rows, SAME date + SAME duration bucket (1.0 h), with
    DIFFERENT tss/coach_comments (and titles), each meant to merge into a
    distinct raw-file workout."""
    rows = [
        {
            "WorkoutDay": "2026-01-11",
            "WorkoutType": "Bike",
            "Title": "Session A",
            "WorkoutDescription": "first",
            "TimeTotalInHours": 1.0,
            "TSS": 70.0,
            "IF": 0.7,
            "PowerAverage": 180.0,
            "DistanceInMeters": 30000.0,
            "HeartRateAverage": 130.0,
            "CoachComments": "ride A coach note",
            "PlannedDuration": None,
        },
        {
            "WorkoutDay": "2026-01-11",
            "WorkoutType": "Bike",
            "Title": "Session B",
            "WorkoutDescription": "second",
            "TimeTotalInHours": 1.0,
            "TSS": 95.0,
            "IF": 0.8,
            "PowerAverage": 200.0,
            "DistanceInMeters": 35000.0,
            "HeartRateAverage": 145.0,
            "CoachComments": "ride B coach note",
            "PlannedDuration": None,
        },
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


async def test_two_same_bucket_summaries_merge_into_distinct_raw_rows(db_session, tmp_path):
    """Two raw-file workouts on the SAME date + SAME duration bucket, plus two
    matching CSV summaries with DIFFERENT tss/coach_comments → the summaries
    merge into the TWO distinct raw rows (1:1), not both into the first.
    Target selection is deterministic (ORDER BY id + consumed-id tracking)."""
    from app.services.ingestion.tp_export_importer import import_athlete_folder
    from sqlalchemy import select

    session, athlete = db_session
    ctx = TenantContext(athlete_id=athlete.id, tenant_id=athlete.tenant_id, role=Role.ATHLETE)

    tp_dir = tmp_path / "TP-2026"
    tp_dir.mkdir()
    # Two raw TCX files: same date+duration, distinct bytes (different HR).
    with zipfile.ZipFile(tp_dir / "WorkoutFileExport-2026.zip", "w") as zf:
        zf.writestr("a1.tcx.gz", gzip.compress(_tcx_with_hr(120, 140)))
        zf.writestr("a2.tcx.gz", gzip.compress(_tcx_with_hr(110, 150)))
    # Two CSV summaries for the same session bucket, distinct tss/comments.
    with zipfile.ZipFile(tp_dir / "WorkoutExport-2026.zip", "w") as zf:
        zf.writestr("workouts.csv", _two_completed_csv_same_bucket())

    report = await import_athlete_folder(session, ctx, athlete.id, tmp_path)
    await session.flush()

    rows = (await session.execute(
        select(WorkoutCompleted).where(
            WorkoutCompleted.athlete_id == athlete.id,
            WorkoutCompleted.deleted_at.is_(None),
        ).order_by(WorkoutCompleted.id)
    )).scalars().all()

    # Two raw rows survive (no new CSV rows created); both are raw-file rows.
    assert len(rows) == 2, f"expected 2 raw rows, got {len(rows)}"
    assert all(r.source_file_id is not None for r in rows)

    # Each CSV summary merged into a DISTINCT raw row: the two distinct TSS
    # values both appear, once each (not the same value on both).
    tss_values = sorted(r.tss for r in rows)
    assert tss_values == pytest.approx([70.0, 95.0]), f"tss not 1:1 distributed: {tss_values}"

    coach_notes = sorted(r.extra.get("coach_comments") for r in rows)
    assert coach_notes == ["ride A coach note", "ride B coach note"], coach_notes

    # Both summaries were merges; neither inserted a new completed row.
    assert report.merged_from_csv == 2
    assert report.workouts_completed == 2  # the two raw-file rows


async def test_two_distinct_rides_same_day_both_survive(db_session, tmp_path):
    """Two CSV rows, same date, same duration bucket, DIFFERENT distance →
    TWO WorkoutCompleted rows (the distance discriminator prevents collision)."""
    from app.services.ingestion.tp_export_importer import import_athlete_folder
    from sqlalchemy import func, select

    session, athlete = db_session
    ctx = TenantContext(athlete_id=athlete.id, tenant_id=athlete.tenant_id, role=Role.ATHLETE)

    rows = [
        {
            "WorkoutDay": "2026-02-01",
            "WorkoutType": "Bike",
            "Title": "Morning",
            "WorkoutDescription": "ride A",
            "TimeTotalInHours": 1.5,   # same duration bucket
            "TSS": 60.0,
            "IF": 0.72,
            "PowerAverage": 185.0,
            "DistanceInMeters": 40000.0,  # distinct distance
            "HeartRateAverage": 135.0,
            "PlannedDuration": None,
        },
        {
            "WorkoutDay": "2026-02-01",
            "WorkoutType": "Bike",
            "Title": "Afternoon",
            "WorkoutDescription": "ride B",
            "TimeTotalInHours": 1.5,   # same duration bucket
            "TSS": 62.0,
            "IF": 0.73,
            "PowerAverage": 190.0,
            "DistanceInMeters": 55000.0,  # distinct distance (>500m apart)
            "HeartRateAverage": 138.0,
            "PlannedDuration": None,
        },
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)

    tp_dir = tmp_path / "TP-2026"
    tp_dir.mkdir()
    with zipfile.ZipFile(tp_dir / "WorkoutExport-2026.zip", "w") as zf:
        zf.writestr("workouts.csv", buf.getvalue())

    report = await import_athlete_folder(session, ctx, athlete.id, tmp_path)
    await session.flush()

    count = (await session.execute(
        select(func.count()).select_from(WorkoutCompleted).where(
            WorkoutCompleted.athlete_id == athlete.id,
            WorkoutCompleted.deleted_at.is_(None),
        )
    )).scalar()
    assert count == 2, f"expected 2 distinct rides, got {count}"
    assert report.workouts_completed == 2


async def test_csv_completed_carries_source_tag(db_session, tmp_path):
    """CSV-derived completed + planned rows carry extra['source']."""
    from app.services.ingestion.tp_export_importer import import_athlete_folder
    from sqlalchemy import select

    session, athlete = db_session
    ctx = TenantContext(athlete_id=athlete.id, tenant_id=athlete.tenant_id, role=Role.ATHLETE)

    _build_fake_folder(tmp_path)
    await import_athlete_folder(session, ctx, athlete.id, tmp_path)
    await session.flush()

    # CSV-summary completed workout (no source_file_id) must carry source in extra
    completed = (await session.execute(
        select(WorkoutCompleted).where(
            WorkoutCompleted.athlete_id == athlete.id,
            WorkoutCompleted.deleted_at.is_(None),
            WorkoutCompleted.source_file_id.is_(None),
        )
    )).scalars().all()
    assert completed, "no CSV-summary completed workout found"
    for w in completed:
        assert w.extra is not None and w.extra.get("source") == "trainingpeaks_export"

    planned = (await session.execute(
        select(WorkoutPlanned).where(
            WorkoutPlanned.athlete_id == athlete.id,
            WorkoutPlanned.deleted_at.is_(None),
        )
    )).scalars().all()
    assert planned, "no planned workout found"
    for p in planned:
        assert p.extra is not None and p.extra.get("source") == "trainingpeaks_export"
