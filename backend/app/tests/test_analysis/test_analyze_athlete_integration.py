"""Integration tests for analyze_athlete CLI persistence layer.

Tests:
1. twin_seed persisted on AthleteProfile after running analysis path.
2. FtpHistory rows created.
3. PowerCurvePoint rows created.
4. Idempotent on re-run (no duplicate rows).

Uses in-memory SQLite (same pattern as test_workout_extra.py / conftest.py).
NO real athlete data.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.core.tenant import TenantContext
from app.models import Base
from app.models.athlete import Athlete, AthleteProfile
from app.models.enums import Role, WorkoutType
from app.models.metrics import FtpHistory, LoadMetric, PowerCurvePoint
from app.models.workout import WorkoutCompleted, WorkoutStream
from app.scripts.analyze_athlete import run_analysis

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Fixture: in-memory SQLite engine + seeded data
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """Create in-memory SQLite with tables + a seeded athlete + minimal data."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        # Create athlete
        athlete = Athlete(
            email="test.athlete@example.com",
            hashed_password=hash_password("pw12345678"),
            full_name="Test Athlete",
            role=Role.ATHLETE,
            tenant_id="tenant_test",
        )
        s.add(athlete)
        await s.flush()

        # Create profile with weight
        profile = AthleteProfile(
            athlete_id=athlete.id,
            weight_kg=75.0,
            primary_discipline="XCO",
        )
        s.add(profile)
        await s.flush()

        # Create workouts with streams (enough for power curve + FTP estimation)
        # 3 workouts with a 25-min constant power stream each
        base_dt = date(2024, 3, 1)
        for i in range(3):
            wdate = date(2024, 3, 1 + i * 7)
            wc = WorkoutCompleted(
                athlete_id=athlete.id,
                started_at=datetime(wdate.year, wdate.month, wdate.day, 8, 0, tzinfo=timezone.utc),
                workout_date=wdate,
                name=f"Test Ride {i+1}",
                workout_type=WorkoutType.ENDURANCE,
                sport="cycling",
                duration_s=25 * 60,
                intensity_factor=0.72,
                tss=80.0,
                extra={"pwr_zone_minutes": [10, 15, 5, 3, 0, 0, 0, 0, 0, 0]},
            )
            s.add(wc)
            await s.flush()

            # Power stream: constant 300W for 25 min
            stream = WorkoutStream(
                athlete_id=athlete.id,
                workout_id=wc.id,
                sample_rate_hz=1.0,
                power=[300.0] * (25 * 60),
            )
            s.add(stream)

        # Create load metrics for block detection
        for day_offset in range(14):
            d = date(2024, 3, 1 + day_offset)
            lm = LoadMetric(
                athlete_id=athlete.id,
                metric_date=d,
                daily_tss=80.0 if day_offset % 7 < 5 else 0.0,
                ctl=50.0 + day_offset * 0.5,
                atl=55.0 + day_offset * 0.3,
                tsb=-5.0 + day_offset * 0.2,
            )
            s.add(lm)

        await s.commit()
        yield s, athlete, profile

    await engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_twin_seed_persisted(db_session, tmp_path):
    """run_analysis persists twin_seed on AthleteProfile."""
    session, athlete, profile = db_session

    await run_analysis(
        session=session,
        athlete_id=athlete.id,
        athlete_name=athlete.full_name,
        output_dir=tmp_path,
        slug="test-athlete",
    )
    await session.commit()

    # Refresh the profile
    await session.refresh(profile)
    assert profile.twin_seed is not None
    assert isinstance(profile.twin_seed, dict)
    assert "ftp_timeline" in profile.twin_seed
    assert "block_summary" in profile.twin_seed


async def test_ftp_history_rows_created(db_session, tmp_path):
    """run_analysis creates at least one FtpHistory row."""
    session, athlete, profile = db_session

    await run_analysis(
        session=session,
        athlete_id=athlete.id,
        athlete_name=athlete.full_name,
        output_dir=tmp_path,
        slug="test-athlete",
    )
    await session.commit()

    stmt = select(FtpHistory).where(
        FtpHistory.athlete_id == athlete.id,
        FtpHistory.deleted_at.is_(None),
    )
    res = await session.execute(stmt)
    rows = list(res.scalars().all())
    assert len(rows) >= 1
    assert rows[0].ftp_watts > 0
    assert rows[0].method in ("estimate_pc20", "estimate_pc60")
    assert rows[0].source == "task2_analysis"


async def test_power_curve_points_created(db_session, tmp_path):
    """run_analysis creates PowerCurvePoint rows for all-time curve."""
    session, athlete, profile = db_session

    await run_analysis(
        session=session,
        athlete_id=athlete.id,
        athlete_name=athlete.full_name,
        output_dir=tmp_path,
        slug="test-athlete",
    )
    await session.commit()

    stmt = select(PowerCurvePoint).where(
        PowerCurvePoint.athlete_id == athlete.id,
        PowerCurvePoint.deleted_at.is_(None),
    )
    res = await session.execute(stmt)
    rows = list(res.scalars().all())
    assert len(rows) >= 1
    # All-time period
    assert any(r.period_label == "all-time" for r in rows)


async def test_idempotent_on_rerun(db_session, tmp_path):
    """Running analysis twice does not duplicate FtpHistory or PowerCurvePoint rows."""
    session, athlete, profile = db_session

    for _ in range(2):
        await run_analysis(
            session=session,
            athlete_id=athlete.id,
            athlete_name=athlete.full_name,
            output_dir=tmp_path,
            slug="test-athlete",
        )
        await session.commit()

    # Count FtpHistory rows
    stmt_ftp = select(FtpHistory).where(
        FtpHistory.athlete_id == athlete.id,
        FtpHistory.deleted_at.is_(None),
    )
    res_ftp = await session.execute(stmt_ftp)
    ftp_rows = list(res_ftp.scalars().all())

    # Count PowerCurvePoint rows
    stmt_pc = select(PowerCurvePoint).where(
        PowerCurvePoint.athlete_id == athlete.id,
        PowerCurvePoint.deleted_at.is_(None),
    )
    res_pc = await session.execute(stmt_pc)
    pc_rows = list(res_pc.scalars().all())

    # After two runs the counts should be the same as after one run
    # (idempotent: update/replace, no duplicates)
    # We verify by running once more and checking counts don't grow
    initial_ftp_count = len(ftp_rows)
    initial_pc_count = len(pc_rows)

    await run_analysis(
        session=session,
        athlete_id=athlete.id,
        athlete_name=athlete.full_name,
        output_dir=tmp_path,
        slug="test-athlete",
    )
    await session.commit()

    res_ftp2 = await session.execute(stmt_ftp)
    ftp_rows2 = list(res_ftp2.scalars().all())
    res_pc2 = await session.execute(stmt_pc)
    pc_rows2 = list(res_pc2.scalars().all())

    assert len(ftp_rows2) == initial_ftp_count, (
        f"FtpHistory rows grew from {initial_ftp_count} to {len(ftp_rows2)} on re-run"
    )
    assert len(pc_rows2) == initial_pc_count, (
        f"PowerCurvePoint rows grew from {initial_pc_count} to {len(pc_rows2)} on re-run"
    )


async def test_report_file_written(db_session, tmp_path):
    """run_analysis writes a markdown report file."""
    session, athlete, profile = db_session

    await run_analysis(
        session=session,
        athlete_id=athlete.id,
        athlete_name=athlete.full_name,
        output_dir=tmp_path,
        slug="test-athlete",
    )
    await session.commit()

    report_file = tmp_path / "test-athlete-perfil.md"
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "Resumo executivo" in content
