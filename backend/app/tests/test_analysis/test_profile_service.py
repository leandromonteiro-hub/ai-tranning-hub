"""Tests for app.services.analysis.profile_service.generate_and_persist_profile.

Covers:
- twin_seed persisted (including data_richness key)
- FtpHistory rows created
- PowerCurvePoint rows created
- Returns the expected summary dict structure
- Idempotent on re-run (no row duplication)
- Creates an AthleteProfile when none exists (freshly-registered athlete)

Uses in-memory SQLite (same pattern as test_analyze_athlete_integration.py).
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
from app.services.analysis.profile_service import generate_and_persist_profile

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(athlete: Athlete) -> TenantContext:
    return TenantContext(
        athlete_id=athlete.id,
        tenant_id=athlete.tenant_id,
        role=athlete.role,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session_with_profile():
    """In-memory SQLite + seeded athlete WITH AthleteProfile + workouts/streams/load_metrics."""
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
        athlete = Athlete(
            email="svc.athlete@example.com",
            hashed_password=hash_password("pw12345678"),
            full_name="Service Athlete",
            role=Role.ATHLETE,
            tenant_id="tenant_svc",
        )
        s.add(athlete)
        await s.flush()

        profile = AthleteProfile(
            athlete_id=athlete.id,
            weight_kg=70.0,
            primary_discipline="XCO",
        )
        s.add(profile)
        await s.flush()

        # Three workouts with power streams (constant 280W for 25 min)
        for i in range(3):
            wdate = date(2024, 4, 1 + i * 7)
            wc = WorkoutCompleted(
                athlete_id=athlete.id,
                started_at=datetime(wdate.year, wdate.month, wdate.day, 8, 0, tzinfo=timezone.utc),
                workout_date=wdate,
                name=f"Svc Ride {i+1}",
                workout_type=WorkoutType.ENDURANCE,
                sport="cycling",
                duration_s=25 * 60,
                intensity_factor=0.72,
                tss=75.0,
                avg_power=280.0,
                extra={"pwr_zone_minutes": [10, 15, 5, 3, 0, 0, 0, 0, 0, 0]},
            )
            s.add(wc)
            await s.flush()

            stream = WorkoutStream(
                athlete_id=athlete.id,
                workout_id=wc.id,
                sample_rate_hz=1.0,
                power=[280.0] * (25 * 60),
            )
            s.add(stream)

        # Load metrics for block detection
        for day_offset in range(14):
            d = date(2024, 4, 1 + day_offset)
            lm = LoadMetric(
                athlete_id=athlete.id,
                metric_date=d,
                daily_tss=75.0 if day_offset % 7 < 5 else 0.0,
                ctl=48.0 + day_offset * 0.5,
                atl=52.0 + day_offset * 0.3,
                tsb=-4.0 + day_offset * 0.2,
            )
            s.add(lm)

        await s.commit()
        yield s, athlete, profile

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_no_profile():
    """In-memory SQLite + seeded athlete WITHOUT AthleteProfile (freshly registered)."""
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
        athlete = Athlete(
            email="noprofile.athlete@example.com",
            hashed_password=hash_password("pw12345678"),
            full_name="No Profile Athlete",
            role=Role.ATHLETE,
            tenant_id="tenant_noprofile",
        )
        s.add(athlete)
        await s.flush()

        # Two workouts with power streams
        for i in range(2):
            wdate = date(2024, 5, 1 + i * 14)
            wc = WorkoutCompleted(
                athlete_id=athlete.id,
                started_at=datetime(wdate.year, wdate.month, wdate.day, 9, 0, tzinfo=timezone.utc),
                workout_date=wdate,
                name=f"No Profile Ride {i+1}",
                workout_type=WorkoutType.ENDURANCE,
                sport="cycling",
                duration_s=30 * 60,
                intensity_factor=0.68,
                tss=70.0,
                avg_power=260.0,
                extra={},
            )
            s.add(wc)
            await s.flush()

            stream = WorkoutStream(
                athlete_id=athlete.id,
                workout_id=wc.id,
                sample_rate_hz=1.0,
                power=[260.0] * (30 * 60),
            )
            s.add(stream)

        await s.commit()
        yield s, athlete

    await engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_twin_seed_persisted_with_richness(db_session_with_profile):
    """generate_and_persist_profile persists twin_seed including data_richness."""
    session, athlete, profile = db_session_with_profile
    ctx = _make_ctx(athlete)

    await generate_and_persist_profile(session, ctx, athlete.id)
    await session.commit()

    await session.refresh(profile)
    assert profile.twin_seed is not None
    assert isinstance(profile.twin_seed, dict)
    assert "ftp_timeline" in profile.twin_seed
    assert "block_summary" in profile.twin_seed
    # T4.2 requirement: richness stored in twin_seed
    assert "data_richness" in profile.twin_seed
    dr = profile.twin_seed["data_richness"]
    assert "score" in dr
    assert "label" in dr
    assert dr["label"] in ("baixa", "média", "alta")


async def test_ftp_history_rows_created(db_session_with_profile):
    """generate_and_persist_profile creates at least one FtpHistory row."""
    session, athlete, profile = db_session_with_profile
    ctx = _make_ctx(athlete)

    await generate_and_persist_profile(session, ctx, athlete.id)
    await session.commit()

    stmt = select(FtpHistory).where(
        FtpHistory.athlete_id == athlete.id,
        FtpHistory.deleted_at.is_(None),
    )
    res = await session.execute(stmt)
    rows = list(res.scalars().all())
    assert len(rows) >= 1
    assert rows[0].ftp_watts > 0
    assert rows[0].source == "task2_analysis"


async def test_power_curve_points_created(db_session_with_profile):
    """generate_and_persist_profile creates PowerCurvePoint rows."""
    session, athlete, profile = db_session_with_profile
    ctx = _make_ctx(athlete)

    await generate_and_persist_profile(session, ctx, athlete.id)
    await session.commit()

    stmt = select(PowerCurvePoint).where(
        PowerCurvePoint.athlete_id == athlete.id,
        PowerCurvePoint.deleted_at.is_(None),
    )
    res = await session.execute(stmt)
    rows = list(res.scalars().all())
    assert len(rows) >= 1
    assert any(r.period_label == "all-time" for r in rows)


async def test_returns_summary_dict(db_session_with_profile):
    """generate_and_persist_profile returns the expected summary dict structure."""
    session, athlete, profile = db_session_with_profile
    ctx = _make_ctx(athlete)

    summary = await generate_and_persist_profile(session, ctx, athlete.id)
    await session.commit()

    assert isinstance(summary, dict)
    assert "n_workouts" in summary
    assert "weeks" in summary
    assert "ftp_recent" in summary
    assert "n_blocks" in summary
    assert "n_races" in summary
    assert "excluded_power_streams" in summary
    assert "richness" in summary

    assert summary["n_workouts"] == 3
    assert isinstance(summary["richness"], dict)
    assert "score" in summary["richness"]
    assert "label" in summary["richness"]


async def test_idempotent_on_rerun(db_session_with_profile):
    """Running the service twice does not duplicate FtpHistory or PowerCurvePoint rows."""
    session, athlete, profile = db_session_with_profile
    ctx = _make_ctx(athlete)

    await generate_and_persist_profile(session, ctx, athlete.id)
    await session.commit()

    stmt_ftp = select(FtpHistory).where(
        FtpHistory.athlete_id == athlete.id,
        FtpHistory.deleted_at.is_(None),
    )
    stmt_pc = select(PowerCurvePoint).where(
        PowerCurvePoint.athlete_id == athlete.id,
        PowerCurvePoint.deleted_at.is_(None),
    )

    res_ftp = await session.execute(stmt_ftp)
    initial_ftp = len(list(res_ftp.scalars().all()))
    res_pc = await session.execute(stmt_pc)
    initial_pc = len(list(res_pc.scalars().all()))

    # Second run
    await generate_and_persist_profile(session, ctx, athlete.id)
    await session.commit()

    res_ftp2 = await session.execute(stmt_ftp)
    final_ftp = len(list(res_ftp2.scalars().all()))
    res_pc2 = await session.execute(stmt_pc)
    final_pc = len(list(res_pc2.scalars().all()))

    assert final_ftp == initial_ftp, (
        f"FtpHistory rows grew from {initial_ftp} to {final_ftp} on re-run"
    )
    assert final_pc == initial_pc, (
        f"PowerCurvePoint rows grew from {initial_pc} to {final_pc} on re-run"
    )


async def test_creates_profile_when_missing(db_session_no_profile):
    """generate_and_persist_profile creates an AthleteProfile if none exists."""
    session, athlete = db_session_no_profile
    ctx = _make_ctx(athlete)

    # Verify no profile exists
    stmt = select(AthleteProfile).where(
        AthleteProfile.athlete_id == athlete.id,
        AthleteProfile.deleted_at.is_(None),
    )
    res = await session.execute(stmt)
    assert res.scalar_one_or_none() is None, "Precondition: profile should not exist"

    # Run service
    summary = await generate_and_persist_profile(session, ctx, athlete.id)
    await session.commit()

    # Profile should now exist with twin_seed
    res2 = await session.execute(stmt)
    new_profile = res2.scalar_one_or_none()
    assert new_profile is not None, "AthleteProfile should have been created"
    assert new_profile.twin_seed is not None
    assert "data_richness" in new_profile.twin_seed

    # Summary should still be valid
    assert summary["n_workouts"] == 2
