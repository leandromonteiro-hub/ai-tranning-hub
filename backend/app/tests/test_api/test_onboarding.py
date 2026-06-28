"""T4.3 / T4 — Onboarding endpoint: POST /imports/trainingpeaks-export.

After Task 4 the endpoint INGESTS inline and ENQUEUES the heavy profile
regeneration on the Celery worker (it no longer builds the profile during the
request). So the response carries ``ingestion`` + ``profile_task_id`` and NO
longer ``profile``/``richness``, and ``twin_seed`` is produced asynchronously.

Tests:
- Athlete A uploads three synthetic TP zips → 200, ingestion counts > 0,
  ``profile_task_id`` present, enqueue called once, no ``profile``/``richness``.
- A has WorkoutCompleted rows inline; simulating the worker regen then yields
  AthleteProfile.twin_seed.
- Isolation: Athlete B has ZERO WorkoutCompleted rows and twin_seed is None.
- Idempotency: A uploads the same zips again → no duplication.
- Path traversal: malicious filenames are sanitized to basename.

Every test patches ``app.api.routes.imports.regenerate_profile_task`` so no real
broker is hit.
"""
from __future__ import annotations

import gzip
import io
import zipfile
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import hash_password
from app.core.tenant import TenantContext
from app.main import app
from app.models import Base
from app.models.athlete import Athlete, AthleteProfile
from app.models.enums import Role
from app.models.workout import WorkoutCompleted
from app.services.analysis.profile_service import generate_and_persist_profile

pytestmark = pytest.mark.asyncio

# Patch target for the enqueue — used by every test that hits the endpoint.
_ENQUEUE_TARGET = "app.api.routes.imports.regenerate_profile_task"

# ---------------------------------------------------------------------------
# Synthetic zip builders (in-test, no real athlete data)
# ---------------------------------------------------------------------------

def _metrics_csv_bytes() -> bytes:
    rows = [
        {"Timestamp": "2026-01-10 06:00:00", "Type": "HRV", "Value": 55.0},
        {"Timestamp": "2026-01-10 06:00:00", "Type": "Pulse", "Value": 48.0},
        {"Timestamp": "2026-01-10 06:00:00", "Type": "Sleep Hours", "Value": 7.5},
        {"Timestamp": "2026-01-11 06:00:00", "Type": "HRV", "Value": 50.0},
        {"Timestamp": "2026-01-11 06:00:00", "Type": "Pulse", "Value": 52.0},
        {"Timestamp": "2026-01-11 06:00:00", "Type": "Sleep Hours", "Value": 6.5},
    ]
    buf = io.BytesIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue()


def _workouts_csv_bytes() -> bytes:
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
    ]
    buf = io.BytesIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue()


_MINIMAL_GPX = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
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


def _build_upload_files() -> list[tuple[str, tuple[str, bytes, str]]]:
    """Return a list of (field_name, (filename, bytes, content-type)) triples
    suitable for httpx multipart upload."""
    # MetricsExport zip
    metrics_buf = io.BytesIO()
    with zipfile.ZipFile(metrics_buf, "w") as zf:
        zf.writestr("metrics.csv", _metrics_csv_bytes())
    metrics_buf.seek(0)

    # WorkoutExport zip
    workouts_buf = io.BytesIO()
    with zipfile.ZipFile(workouts_buf, "w") as zf:
        zf.writestr("workouts.csv", _workouts_csv_bytes())
    workouts_buf.seek(0)

    # WorkoutFileExport zip — contains one .gpx.gz
    files_buf = io.BytesIO()
    with zipfile.ZipFile(files_buf, "w") as zf:
        zf.writestr("activity_20260111.gpx.gz", gzip.compress(_MINIMAL_GPX))
    files_buf.seek(0)

    return [
        ("files", ("MetricsExport-2026.zip", metrics_buf.getvalue(), "application/zip")),
        ("files", ("WorkoutExport-2026.zip", workouts_buf.getvalue(), "application/zip")),
        ("files", ("WorkoutFileExport-2026.zip", files_buf.getvalue(), "application/zip")),
    ]


# ---------------------------------------------------------------------------
# Fixture: two athletes A and B
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
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
        s.add(Athlete(
            email="athlete_a@example.com",
            hashed_password=hash_password("pw12345678"),
            full_name="Athlete A",
            role=Role.ATHLETE,
            tenant_id="tenant_a",
        ))
        s.add(Athlete(
            email="athlete_b@example.com",
            hashed_password=hash_password("pw12345678"),
            full_name="Athlete B",
            role=Role.ATHLETE,
            tenant_id="tenant_b",
        ))
        await s.commit()

    async def _override_get_db():
        async with maker() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def _token(client: AsyncClient, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "pw12345678"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_onboarding_endpoint_returns_200_with_ingestion_and_task_id(client):
    """Athlete A uploads TP export zips → 200 with ingestion counts + an async
    ``profile_task_id`` (enqueue called once); no inline profile/richness."""
    token_a = await _token(client, "athlete_a@example.com")
    headers = {"Authorization": f"Bearer {token_a}"}

    with patch(_ENQUEUE_TARGET) as t:
        t.delay.return_value = MagicMock(id="onb-task")
        r = await client.post(
            "/api/v1/imports/trainingpeaks-export",
            headers=headers,
            files=_build_upload_files(),
        )
    assert r.status_code == 200, r.text

    body = r.json()
    # Ingestion summary present with counts
    assert "ingestion" in body
    ingestion = body["ingestion"]
    # At least the CSV-completed workout + the GPX raw workout were created
    assert ingestion["workouts_completed"] >= 1
    # Recovery days from metrics.csv (2 days of HRV)
    assert ingestion["recovery_days"] >= 1

    # Profile regeneration was enqueued and its id surfaced.
    t.delay.assert_called_once()
    assert body.get("profile_task_id"), "profile_task_id missing/empty"
    assert body["profile_task_id"] == "onb-task"

    # Profile/richness are now produced async — NOT in the response.
    assert "profile" not in body
    assert "richness" not in body


async def test_athlete_a_has_workouts_and_twin_seed_after_upload(client):
    """The endpoint creates WorkoutCompleted rows inline; the (now async) profile
    regen — simulated here by running it against the test DB — yields twin_seed."""
    from app.core.database import get_db as real_get_db

    token_a = await _token(client, "athlete_a@example.com")
    headers = {"Authorization": f"Bearer {token_a}"}

    with patch(_ENQUEUE_TARGET) as t:
        t.delay.return_value = MagicMock(id="onb-task")
        r = await client.post(
            "/api/v1/imports/trainingpeaks-export",
            headers=headers,
            files=_build_upload_files(),
        )
    assert r.status_code == 200, r.text

    # Verify via the overridden DB session
    session_factory = app.dependency_overrides[real_get_db]
    async for db in session_factory():
        # Get athlete A's id
        res = await db.execute(
            select(Athlete).where(Athlete.email == "athlete_a@example.com")
        )
        athlete_a = res.scalar_one()

        # WorkoutCompleted rows were created INLINE by the endpoint.
        wc_count = (await db.execute(
            select(func.count()).select_from(WorkoutCompleted).where(
                WorkoutCompleted.athlete_id == athlete_a.id,
                WorkoutCompleted.deleted_at.is_(None),
            )
        )).scalar()
        assert wc_count >= 1, f"Expected workouts for A, got {wc_count}"

        # Simulate the Celery worker: run the profile regen against the test DB.
        ctx = TenantContext(
            athlete_id=athlete_a.id, tenant_id="tenant_a", role=Role.ATHLETE
        )
        await generate_and_persist_profile(db, ctx, athlete_a.id)
        await db.commit()

        # AthleteProfile with twin_seed now exists.
        profile_res = await db.execute(
            select(AthleteProfile).where(
                AthleteProfile.athlete_id == athlete_a.id,
                AthleteProfile.deleted_at.is_(None),
            )
        )
        profile = profile_res.scalar_one_or_none()
        assert profile is not None, "AthleteProfile not created for A"
        assert profile.twin_seed is not None, "twin_seed not set for A"
        assert "data_richness" in profile.twin_seed
        break


async def test_isolation_athlete_b_unaffected_after_a_uploads(client):
    """After A's upload, Athlete B has ZERO WorkoutCompleted rows and twin_seed is
    None (B never had a regen)."""
    from app.core.database import get_db as real_get_db

    token_a = await _token(client, "athlete_a@example.com")
    with patch(_ENQUEUE_TARGET) as t:
        t.delay.return_value = MagicMock(id="onb-task")
        r = await client.post(
            "/api/v1/imports/trainingpeaks-export",
            headers={"Authorization": f"Bearer {token_a}"},
            files=_build_upload_files(),
        )
    assert r.status_code == 200, r.text

    # Now check athlete B's data
    session_factory = app.dependency_overrides[real_get_db]
    async for db in session_factory():
        res = await db.execute(
            select(Athlete).where(Athlete.email == "athlete_b@example.com")
        )
        athlete_b = res.scalar_one()

        # B has ZERO WorkoutCompleted rows
        wc_count = (await db.execute(
            select(func.count()).select_from(WorkoutCompleted).where(
                WorkoutCompleted.athlete_id == athlete_b.id,
                WorkoutCompleted.deleted_at.is_(None),
            )
        )).scalar()
        assert wc_count == 0, f"Isolation FAILED: B has {wc_count} WorkoutCompleted rows"

        # B has no AthleteProfile (or twin_seed is None)
        profile_res = await db.execute(
            select(AthleteProfile).where(
                AthleteProfile.athlete_id == athlete_b.id,
                AthleteProfile.deleted_at.is_(None),
            )
        )
        profile_b = profile_res.scalar_one_or_none()
        if profile_b is not None:
            assert profile_b.twin_seed is None, (
                f"Isolation FAILED: B has twin_seed = {profile_b.twin_seed}"
            )
        break


async def test_idempotency_second_upload_no_duplication(client):
    """A second identical upload by A does not duplicate WorkoutCompleted rows."""
    from app.core.database import get_db as real_get_db

    token_a = await _token(client, "athlete_a@example.com")
    headers = {"Authorization": f"Bearer {token_a}"}

    # First upload
    with patch(_ENQUEUE_TARGET) as t:
        t.delay.return_value = MagicMock(id="onb-task")
        r1 = await client.post(
            "/api/v1/imports/trainingpeaks-export",
            headers=headers,
            files=_build_upload_files(),
        )
    assert r1.status_code == 200, r1.text

    # Count rows after first upload
    session_factory = app.dependency_overrides[real_get_db]
    count_after_first = None
    async for db in session_factory():
        res = await db.execute(
            select(Athlete).where(Athlete.email == "athlete_a@example.com")
        )
        athlete_a = res.scalar_one()
        count_after_first = (await db.execute(
            select(func.count()).select_from(WorkoutCompleted).where(
                WorkoutCompleted.athlete_id == athlete_a.id,
                WorkoutCompleted.deleted_at.is_(None),
            )
        )).scalar()
        break

    # Second upload (same files)
    with patch(_ENQUEUE_TARGET) as t:
        t.delay.return_value = MagicMock(id="onb-task")
        r2 = await client.post(
            "/api/v1/imports/trainingpeaks-export",
            headers=headers,
            files=_build_upload_files(),
        )
    assert r2.status_code == 200, r2.text

    # Count rows after second upload — must be identical
    async for db in session_factory():
        res = await db.execute(
            select(Athlete).where(Athlete.email == "athlete_a@example.com")
        )
        athlete_a = res.scalar_one()
        count_after_second = (await db.execute(
            select(func.count()).select_from(WorkoutCompleted).where(
                WorkoutCompleted.athlete_id == athlete_a.id,
                WorkoutCompleted.deleted_at.is_(None),
            )
        )).scalar()
        assert count_after_second == count_after_first, (
            f"Idempotency FAILED: count grew {count_after_first} → {count_after_second}"
        )
        break


async def test_path_traversal_filename_is_sanitized_to_basename(client, tmp_path):
    """A malicious upload filename (``../`` / absolute) is staged by BASENAME only.

    The endpoint must not write outside its TemporaryDirectory. We send the
    WorkoutExport zip with a traversal filename ``../WorkoutExport-evil.zip`` and a
    metrics zip with an absolute-path filename; the upload must still be ingested
    (basename preserves the classification prefix), and NO file is created at the
    traversal target on disk.
    """
    import os

    token_a = await _token(client, "athlete_a@example.com")
    headers = {"Authorization": f"Bearer {token_a}"}

    # Build the three zips, but give two of them malicious filenames.
    files = _build_upload_files()
    # files[0] = MetricsExport, files[1] = WorkoutExport, files[2] = WorkoutFileExport
    _, (_, metrics_bytes, ct0) = files[0]
    _, (_, workouts_bytes, ct1) = files[1]
    _, (_, wfe_bytes, ct2) = files[2]

    # A sentinel target the traversal would hit if the basename guard were missing.
    # The absolute-path filename below has basename "MetricsExport-evil.zip", so
    # only writing OUTSIDE the temp dir (under tmp_path here) would create this
    # exact file — its presence proves a traversal escape.
    traversal_target = tmp_path / "MetricsExport-evil.zip"
    assert not traversal_target.exists()

    malicious_files = [
        # Absolute path filename — Path(tmp) / absolute would REPLACE the base.
        # Basename = "MetricsExport-evil.zip" → still classified as MetricsExport
        # (prefix preserved) and ingested normally once sanitized to basename.
        ("files", (str(traversal_target), metrics_bytes, ct0)),
        # Relative traversal filename. Basename = "WorkoutExport-evil.zip" → still
        # classified as a WorkoutExport (prefix preserved), ingested normally.
        ("files", ("../WorkoutExport-evil.zip", workouts_bytes, ct1)),
        ("files", ("../../WorkoutFileExport-evil.zip", wfe_bytes, ct2)),
    ]

    with patch(_ENQUEUE_TARGET) as t:
        t.delay.return_value = MagicMock(id="onb-task")
        r = await client.post(
            "/api/v1/imports/trainingpeaks-export",
            headers=headers,
            files=malicious_files,
        )
    assert r.status_code == 200, r.text

    # Nothing was written to the traversal target (no arbitrary file write).
    assert not traversal_target.exists(), "path traversal: file written outside temp dir"
    assert not os.path.exists("MetricsExport-evil.zip"), "path traversal: file written to cwd"

    # The upload was still ingested normally (basename preserved the prefixes).
    body = r.json()
    assert body["ingestion"]["workouts_completed"] >= 1
    assert body["ingestion"]["recovery_days"] >= 1
