"""TrainingPeaks export folder orchestrator (ST4).

Idempotency strategy
--------------------
Three independent dedup layers ensure a second run produces 0 new rows:

1. **Raw activity files** (.fit/.tcx/.gpx inside .gz files):
   Gunzipped bytes are fed to ``import_file``, which deduplicates by
   SHA-256 content hash of the file bytes. On a second run, ``import_file``
   finds the existing ``ImportedFile`` row and returns ``workouts_created=0``.

2. **workouts.csv completed summaries** (NormalizedActivity from CSV):
   Deduped by natural key ``(athlete_id, workout_date, duration_s_bucket)``
   where ``duration_s_bucket = round(duration_s / 60)`` (1-minute precision).
   On a second run we query for an existing row before inserting.
   **Cross-dedup**: if a raw-file workout already covers the same
   (workout_date, duration_s ± 60 s), we skip the CSV summary entirely
   (prefer the raw-file row since it carries streams). This is implemented by
   collecting raw-file workout keys FIRST, then filtering CSV completed.

3. **workouts.csv planned** (TpPlanned):
   Deduped by natural key ``(athlete_id, planned_date, name)``.
   Query-before-insert, skip if found.

4. **metrics.csv** (RecoveryMetric / SubjectiveMetric):
   Each table has a ``UniqueConstraint(athlete_id, metric_date)``.
   We query-then-update-or-insert so re-runs update in-place instead of
   raising an IntegrityError.

Import order: metrics first → then CSV workouts → then raw files.
``recompute_load_metrics`` is called once at the end.
"""
from __future__ import annotations

import gzip
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.models.metrics import RecoveryMetric, SubjectiveMetric
from app.models.workout import WorkoutCompleted, WorkoutPlanned
from app.repositories.metrics_repo import RecoveryRepository, SubjectiveRepository
from app.repositories.workout_repo import WorkoutRepository
from app.services.ingestion.ingestion_service import import_file
from app.services.ingestion.tp_metrics import TpDailyMetric, parse_tp_metrics
from app.services.ingestion.tp_workouts import TpPlanned, parse_tp_workouts
from app.services.metrics.recompute import recompute_load_metrics

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class IngestionReport:
    """Summary of what was ingested from a TrainingPeaks export folder."""

    # Counts
    workouts_completed: int = 0
    workouts_planned: int = 0
    rest_days: int = 0
    recovery_days: int = 0
    subjective_days: int = 0
    duplicates_skipped: int = 0

    # Period covered
    period_start: date | None = None
    period_end: date | None = None

    # Coverage percentages (0–100)
    pct_power: float = 0.0   # completed workouts with avg_power / total
    pct_hr: float = 0.0      # completed workouts with avg_hr / total
    pct_hrv: float = 0.0     # recovery days with hrv_ms / total recovery days

    # Quality
    unmapped_metric_types: dict = field(default_factory=dict)
    anomalies: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _bucket(duration_s: int | None) -> int | None:
    """Round duration to nearest minute for natural-key dedup."""
    if duration_s is None:
        return None
    return round(duration_s / 60)


def _detect_anomalies(
    completed_workouts: list[WorkoutCompleted],
) -> list[str]:
    anomalies: list[str] = []
    for w in completed_workouts:
        if w.duration_s is not None and w.duration_s > 16 * 3600:
            anomalies.append(
                f"duration>16h on {w.workout_date}: {w.duration_s / 3600:.1f}h"
            )
        if w.tss is not None and w.tss > 700:
            anomalies.append(f"tss>700 on {w.workout_date}: {w.tss:.0f}")
        if w.avg_power is not None and w.avg_power < 0:
            anomalies.append(f"negative avg_power on {w.workout_date}: {w.avg_power}")
        if w.avg_hr is not None and w.avg_hr < 0:
            anomalies.append(f"negative avg_hr on {w.workout_date}: {w.avg_hr}")
    return anomalies


async def _upsert_recovery(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    metric: TpDailyMetric,
    source: str,
) -> bool:
    """Upsert a RecoveryMetric row; return True if a new row was created."""
    repo = RecoveryRepository(session, ctx)
    stmt = (
        select(RecoveryMetric)
        .where(RecoveryMetric.deleted_at.is_(None))
        .where(RecoveryMetric.athlete_id == athlete_id)
        .where(RecoveryMetric.metric_date == metric.metric_date)
    )
    res = await session.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing:
        # Update in place — never duplicate
        if metric.hrv_ms is not None:
            existing.hrv_ms = metric.hrv_ms
        if metric.resting_hr is not None:
            existing.resting_hr = metric.resting_hr
        if metric.sleep_hours is not None:
            existing.sleep_hours = metric.sleep_hours
        existing.source = source
        session.add(existing)
        await session.flush()
        return False
    else:
        row = RecoveryMetric(
            athlete_id=athlete_id,
            metric_date=metric.metric_date,
            hrv_ms=metric.hrv_ms,
            resting_hr=metric.resting_hr,
            sleep_hours=metric.sleep_hours,
            source=source,
            created_by=athlete_id,
        )
        await repo.add(row)
        return True


async def _upsert_subjective(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    metric: TpDailyMetric,
    source: str,
) -> bool:
    """Upsert a SubjectiveMetric for the comment field; return True if new."""
    if not metric.comment:
        return False

    repo = SubjectiveRepository(session, ctx)
    stmt = (
        select(SubjectiveMetric)
        .where(SubjectiveMetric.deleted_at.is_(None))
        .where(SubjectiveMetric.athlete_id == athlete_id)
        .where(SubjectiveMetric.metric_date == metric.metric_date)
    )
    res = await session.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing:
        existing.comment = metric.comment
        session.add(existing)
        await session.flush()
        return False
    else:
        row = SubjectiveMetric(
            athlete_id=athlete_id,
            metric_date=metric.metric_date,
            comment=metric.comment,
            created_by=athlete_id,
        )
        await repo.add(row)
        return True


async def _persist_completed_csv(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    act,
    raw_file_keys: set[tuple],
    source: str,
) -> bool:
    """Persist a CSV-derived completed workout; return True if inserted.

    Cross-dedup: if a raw-file workout already covers (workout_date, bucket)
    skip this CSV summary (prefer the raw-file row which carries streams).
    Natural-key dedup: (athlete_id, workout_date, duration_bucket).
    """
    workout_date = act.started_at.date()
    bucket = _bucket(act.duration_s)

    # Cross-dedup: skip if a raw-file workout was already ingested for this
    # date/duration combination (within ±60 s → same bucket).
    if (workout_date, bucket) in raw_file_keys:
        log.debug(
            "csv_completed_skipped_raw_file_covers",
            extra={"date": str(workout_date), "bucket": bucket},
        )
        return False

    # Natural-key dedup
    stmt = (
        select(WorkoutCompleted)
        .where(WorkoutCompleted.deleted_at.is_(None))
        .where(WorkoutCompleted.athlete_id == athlete_id)
        .where(WorkoutCompleted.workout_date == workout_date)
    )
    res = await session.execute(stmt)
    existing_on_date = res.scalars().all()
    for ex in existing_on_date:
        ex_bucket = _bucket(ex.duration_s)
        if ex_bucket is not None and bucket is not None and ex_bucket == bucket:
            return False

    from app.models.enums import WorkoutType
    from app.repositories.metrics_repo import FtpRepository
    from app.repositories.workout_repo import WorkoutRepository as WR
    from app.services.metrics import tss_calculator

    workout_repo = WR(session, ctx)
    ftp_repo = FtpRepository(session, ctx)
    ftp = await ftp_repo.value_on(workout_date, athlete_id)

    tss = act.source_tss
    intf = act.source_if
    np_value = None
    if act.avg_power and ftp and act.duration_s:
        np_value = act.source_np or act.avg_power
        intf = tss_calculator.intensity_factor(np_value, ftp) or intf
        tss = tss_calculator.tss_from_np(act.duration_s, np_value, ftp) or tss

    workout = WorkoutCompleted(
        athlete_id=athlete_id,
        started_at=act.started_at,
        workout_date=workout_date,
        name=act.name,
        workout_type=act.workout_type,
        sport=act.sport,
        duration_s=act.duration_s,
        distance_m=act.distance_m,
        avg_power=act.avg_power,
        normalized_power=np_value or act.source_np,
        avg_hr=act.avg_hr,
        max_hr=act.max_hr,
        avg_cadence=act.avg_cadence,
        intensity_factor=intf,
        tss=tss,
        ftp_used=ftp,
        notes=act.notes,
        extra=act.extra or None,
        created_by=athlete_id,
    )
    # source field: WorkoutCompleted doesn't have a source column;
    # source provenance is captured in extra or source_file_id
    await workout_repo.add(workout)
    return True


async def _persist_planned(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    tp: TpPlanned,
    source: str,
) -> bool:
    """Persist a planned workout; return True if inserted.

    Natural-key dedup by (athlete_id, planned_date, name).
    """
    stmt = (
        select(WorkoutPlanned)
        .where(WorkoutPlanned.deleted_at.is_(None))
        .where(WorkoutPlanned.athlete_id == athlete_id)
        .where(WorkoutPlanned.planned_date == tp.planned_date)
        .where(WorkoutPlanned.name == tp.name)
    )
    res = await session.execute(stmt)
    if res.scalar_one_or_none():
        return False

    row = WorkoutPlanned(
        athlete_id=athlete_id,
        planned_date=tp.planned_date,
        name=tp.name,
        workout_type=tp.workout_type,
        planned_duration_s=tp.planned_duration_s,
        planned_tss=tp.planned_tss,
        description=tp.description,
        extra=tp.extra or None,
        created_by=athlete_id,
    )
    session.add(row)
    await session.flush()
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def import_athlete_folder(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    folder: Path,
    source: str = "trainingpeaks_export",
) -> IngestionReport:
    """Ingest all TrainingPeaks export zips under ``folder`` idempotently.

    ``folder`` may contain year-named subdirs (e.g. TP-2025/, TP-2026/) or
    have zips directly at top-level. All ``*.zip`` files are found recursively.

    Three zip patterns are handled by filename prefix (case-insensitive):
    - MetricsExport-*.zip         → metrics.csv (long format)
    - WorkoutExport-*.zip         → workouts.csv (wide format)
    - WorkoutFileExport-*.zip     → raw activity files (.fit.gz/.tcx.gz/.gpx.gz)

    Idempotency:
    - metrics: upsert by (athlete_id, metric_date)
    - completed workouts: natural-key dedup by (athlete_id, workout_date, duration_bucket)
    - raw files: content-hash dedup via import_file
    - planned workouts: natural-key dedup by (athlete_id, planned_date, name)
    - cross-dedup: when raw file covers (workout_date, duration±60s), skip CSV summary
    """
    report = IngestionReport()
    all_dates: list[date] = []

    # ------------------------------------------------------------------ #
    # 1. Discover and classify zips                                        #
    # ------------------------------------------------------------------ #
    metrics_zips: list[Path] = []
    workout_zips: list[Path] = []
    file_zips: list[Path] = []

    for z in sorted(folder.rglob("*.zip")):
        name_lower = z.name.lower()
        if name_lower.startswith("metricsexport"):
            metrics_zips.append(z)
        elif name_lower.startswith("workoutfileexport"):
            file_zips.append(z)
        elif name_lower.startswith("workoutexport"):
            workout_zips.append(z)
        else:
            log.warning("tp_unknown_zip", extra={"zip": str(z.name)})

    log.info(
        "tp_folder_discovered",
        extra={
            "metrics_zips": len(metrics_zips),
            "workout_zips": len(workout_zips),
            "file_zips": len(file_zips),
        },
    )

    # ------------------------------------------------------------------ #
    # 2. Metrics                                                           #
    # ------------------------------------------------------------------ #
    for zip_path in metrics_zips:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp_dir)
            for csv_path in Path(tmp_dir).rglob("metrics.csv"):
                data = csv_path.read_bytes()
                metrics, m_report = parse_tp_metrics(data)

                # Merge unmapped types
                for k, v in m_report.get("unmapped_types", {}).items():
                    report.unmapped_metric_types[k] = (
                        report.unmapped_metric_types.get(k, 0) + v
                    )

                for m in metrics:
                    is_new_rec = await _upsert_recovery(
                        session, ctx, athlete_id, m, source
                    )
                    if is_new_rec:
                        report.recovery_days += 1
                    is_new_sub = await _upsert_subjective(
                        session, ctx, athlete_id, m, source
                    )
                    if is_new_sub:
                        report.subjective_days += 1
                    all_dates.append(m.metric_date)

    # ------------------------------------------------------------------ #
    # 3. Raw activity files (import_file with content-hash dedup)          #
    # ------------------------------------------------------------------ #
    # Collect keys (workout_date, duration_bucket) for cross-dedup below.
    raw_file_keys: set[tuple] = set()
    raw_files_total_created = 0

    for zip_path in file_zips:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp_dir)
            for gz_path in Path(tmp_dir).rglob("*"):
                lower = gz_path.name.lower()
                if not (lower.endswith(".fit.gz") or lower.endswith(".tcx.gz")
                        or lower.endswith(".gpx.gz")):
                    continue
                if not gz_path.is_file():
                    continue
                try:
                    decompressed = gzip.decompress(gz_path.read_bytes())
                except Exception as exc:
                    log.warning(
                        "tp_gz_decompress_failed",
                        extra={"file": gz_path.name, "error": str(exc)},
                    )
                    continue

                # Strip the .gz suffix for format detection
                inner_name = gz_path.name[:-3]  # e.g. activity.gpx
                result = await import_file(
                    session, ctx, athlete_id, inner_name, decompressed, source
                )
                report.duplicates_skipped += result.duplicates_skipped
                raw_files_total_created += result.workouts_created

                if result.workouts_created > 0 and result.imported_file.status.value == "completed":
                    # Record keys of newly created workouts for cross-dedup
                    repo = WorkoutRepository(session, ctx)
                    # Fetch workouts created from this file
                    from sqlalchemy import select as sa_select
                    stmt = (
                        sa_select(WorkoutCompleted)
                        .where(WorkoutCompleted.deleted_at.is_(None))
                        .where(WorkoutCompleted.athlete_id == athlete_id)
                        .where(WorkoutCompleted.source_file_id == result.imported_file.id)
                    )
                    res = await session.execute(stmt)
                    for w in res.scalars().all():
                        raw_file_keys.add((w.workout_date, _bucket(w.duration_s)))
                        all_dates.append(w.workout_date)

    # ------------------------------------------------------------------ #
    # 4. Workouts CSV                                                      #
    # ------------------------------------------------------------------ #
    csv_completed_created = 0
    csv_planned_created = 0

    for zip_path in workout_zips:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp_dir)
            for csv_path in Path(tmp_dir).rglob("workouts.csv"):
                data = csv_path.read_bytes()
                completed_acts, planned_acts, w_report = parse_tp_workouts(data)

                report.rest_days += w_report.get("rest_days", 0)

                for act in completed_acts:
                    inserted = await _persist_completed_csv(
                        session, ctx, athlete_id, act, raw_file_keys, source
                    )
                    if inserted:
                        csv_completed_created += 1
                        all_dates.append(act.started_at.date())
                    else:
                        report.duplicates_skipped += 1

                for tp in planned_acts:
                    inserted = await _persist_planned(
                        session, ctx, athlete_id, tp, source
                    )
                    if inserted:
                        csv_planned_created += 1
                        all_dates.append(tp.planned_date)
                    else:
                        report.duplicates_skipped += 1

    # ------------------------------------------------------------------ #
    # 5. Finalise counts                                                   #
    # ------------------------------------------------------------------ #
    report.workouts_completed = raw_files_total_created + csv_completed_created
    report.workouts_planned = csv_planned_created

    # Period
    if all_dates:
        report.period_start = min(all_dates)
        report.period_end = max(all_dates)

    # Coverage: query the DB for final state
    wc_repo = WorkoutRepository(session, ctx)
    from sqlalchemy import func as sa_func
    all_completed = await wc_repo.list_between(
        report.period_start or date(2000, 1, 1),
        report.period_end or date(2099, 12, 31),
        athlete_id,
    )
    total_c = len(all_completed)
    if total_c:
        with_power = sum(1 for w in all_completed if w.avg_power is not None)
        with_hr = sum(1 for w in all_completed if w.avg_hr is not None)
        report.pct_power = 100.0 * with_power / total_c
        report.pct_hr = 100.0 * with_hr / total_c

    rec_repo = RecoveryRepository(session, ctx)
    all_rec = await rec_repo.list_recent(
        report.period_start or date(2000, 1, 1), athlete_id
    )
    total_rec = len(all_rec)
    if total_rec:
        with_hrv = sum(1 for r in all_rec if r.hrv_ms is not None)
        report.pct_hrv = 100.0 * with_hrv / total_rec
        # If recovery_days was only tracking new inserts, sync with actual total
        if report.recovery_days == 0:
            report.recovery_days = total_rec

    # Anomalies
    report.anomalies = _detect_anomalies(all_completed)

    # ------------------------------------------------------------------ #
    # 6. Recompute load metrics                                            #
    # ------------------------------------------------------------------ #
    await recompute_load_metrics(session, ctx, athlete_id)

    log.info(
        "tp_folder_ingested",
        extra={
            "athlete_id": str(athlete_id),
            "workouts_completed": report.workouts_completed,
            "workouts_planned": report.workouts_planned,
            "recovery_days": report.recovery_days,
            "duplicates_skipped": report.duplicates_skipped,
        },
    )
    return report
