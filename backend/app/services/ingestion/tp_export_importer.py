"""TrainingPeaks export folder orchestrator (ST4).

Idempotency strategy
--------------------
Three independent dedup layers ensure a second run produces 0 new rows:

1. **Raw activity files** (.fit/.tcx/.gpx inside .gz files):
   Gunzipped bytes are fed to ``import_file``, which deduplicates by
   SHA-256 content hash of the file bytes. On a second run, ``import_file``
   finds the existing ``ImportedFile`` row and returns ``workouts_created=0``.

2. **workouts.csv completed summaries** (NormalizedActivity from CSV):
   Two distinct dedup keys are used (a CSV row is skipped if EITHER matches):

   - **Cross-source key** ``(workout_date, duration_bucket)`` — duration only,
     NO distance. Used to detect that a CSV summary's raw-file twin
     (FIT/GPX/TCX) was already imported. Distance is intentionally excluded:
     it is NOT stable across sources (GPS smoothing, TP rounding, FIT
     total-vs-moving), so the same physical session can straddle a 500 m
     bucket boundary and double-count. Date+duration is reliable.
   - **Within-CSV key** ``(workout_date, duration_bucket, distance_disc)`` where
     ``distance_disc = round(distance_m / 500)`` (500 m) when distance present,
     else the workout name. Used against already-persisted CSV-derived rows so
     two DISTINCT same-day, same-duration rides both survive, while re-running
     the SAME CSV still dedups.

   Raw-file cross-source keys are collected FIRST (raw files imported before the
   workouts CSV), then each CSV completed row is filtered against them.

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
    """Summary of what was ingested from a TrainingPeaks export folder.

    Field semantics (stable & comparable across runs):

    - **Counts** (``workouts_completed``, ``workouts_planned``, ``rest_days``,
      ``recovery_days``, ``subjective_days``, ``duplicates_skipped``) mean
      "rows created/affected THIS run". On a fully-idempotent second run these
      are 0 (and ``duplicates_skipped`` reflects the rows that were already
      present).
    - **Period** (``period_start`` / ``period_end``) is derived from the DATES
      PARSED OUT OF THE FILES (metrics + workouts), independent of whether rows
      were newly created. A second run reports the same real period.
    - **Coverage %** (``pct_power`` / ``pct_hr`` / ``pct_hrv``) is computed over
      THIS run's parsed dataset, so it is stable and comparable across runs:
        * pct_power = parsed completed activities with avg_power / parsed completed
        * pct_hr    = parsed completed activities with avg_hr / parsed completed
        * pct_hrv   = parsed recovery days with hrv_ms / parsed recovery days
    - ``unmapped_metric_types`` and ``anomalies`` are quality signals over the
      parsed dataset of this run.
    """

    # Counts (rows created/affected THIS run)
    workouts_completed: int = 0
    workouts_planned: int = 0
    rest_days: int = 0
    recovery_days: int = 0
    subjective_days: int = 0
    duplicates_skipped: int = 0

    # Period covered (from PARSED file dates, stable across runs)
    period_start: date | None = None
    period_end: date | None = None

    # Coverage percentages (0–100) over THIS run's parsed dataset
    pct_power: float = 0.0   # parsed completed activities with avg_power / total
    pct_hr: float = 0.0      # parsed completed activities with avg_hr / total
    pct_hrv: float = 0.0     # parsed recovery days with hrv_ms / total

    # Quality (over parsed dataset)
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


def _distance_disc(distance_m: float | None, name: str | None) -> object:
    """Distance discriminator for the WITHIN-CSV natural key.

    Returns ``round(distance_m / 500)`` (500 m buckets) when distance is
    present, else falls back to the workout name (or "" when both absent).
    This keeps two DISTINCT rides on the same day with a similar duration from
    colliding (so both survive within the CSV).
    """
    if distance_m is not None:
        return round(distance_m / 500)
    return name or ""


def _cross_source_key(workout_date: date, duration_s: int | None) -> tuple:
    """CSV-row vs RAW-FILE-workout dedup key: ``(date, duration_bucket)``.

    Duration only — NO distance. The same physical session reliably shares
    date+duration across sources, but distance is NOT stable across sources
    (GPS smoothing, TP rounding, FIT total-vs-moving), so including distance
    here would let a CSV summary and its raw-file twin straddle a bucket
    boundary and double-count.
    """
    return (workout_date, _bucket(duration_s))


def _within_csv_key(
    workout_date: date,
    duration_s: int | None,
    distance_m: float | None,
    name: str | None,
) -> tuple:
    """CSV-row vs already-persisted CSV-derived-row dedup key.

    ``(date, duration_bucket, distance_disc)`` — keeps two distinct same-day,
    same-duration rides both alive while a re-run of the SAME CSV still dedups.
    """
    return (workout_date, _bucket(duration_s), _distance_disc(distance_m, name))


def _detect_anomalies(parsed_completed: list) -> list[str]:
    """Detect anomalies over THIS run's parsed completed activities.

    Operates on parsed ``NormalizedActivity`` objects (not persisted rows) so
    the result is stable and comparable across idempotent re-runs.
    """
    anomalies: list[str] = []
    for act in parsed_completed:
        d = act.started_at.date()
        if act.duration_s is not None and act.duration_s > 16 * 3600:
            anomalies.append(f"duration>16h on {d}: {act.duration_s / 3600:.1f}h")
        if act.source_tss is not None and act.source_tss > 700:
            anomalies.append(f"tss>700 on {d}: {act.source_tss:.0f}")
        if act.avg_power is not None and act.avg_power < 0:
            anomalies.append(f"negative avg_power on {d}: {act.avg_power}")
        if act.avg_hr is not None and act.avg_hr < 0:
            anomalies.append(f"negative avg_hr on {d}: {act.avg_hr}")
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

    A CSV completed row is skipped if EITHER:
      (a) its CROSS-SOURCE key ``(date, duration_bucket)`` is in
          ``raw_file_keys`` — its raw-file twin was already imported (prefer the
          raw row which carries streams), OR
      (b) its WITHIN-CSV key ``(date, duration_bucket, distance_disc)`` matches
          an already-persisted CSV-derived row (re-run idempotency / true dup).
    Otherwise the row is persisted.

    Cross-source uses duration only (distance is not stable across sources);
    within-CSV adds a distance/name discriminator so two distinct same-day
    same-duration rides both survive.
    """
    workout_date = act.started_at.date()
    cross_key = _cross_source_key(workout_date, act.duration_s)
    within_key = _within_csv_key(workout_date, act.duration_s, act.distance_m, act.name)

    # (a) Cross-source dedup: a raw-file twin already covers (date, duration).
    if cross_key in raw_file_keys:
        log.debug(
            "csv_completed_skipped_raw_file_covers",
            extra={"date": str(workout_date), "cross_key": str(cross_key)},
        )
        return False

    # (b) Within-CSV dedup against already-persisted CSV-derived rows on the
    #     same date (exclude raw-file rows, which carry a source_file_id —
    #     those are handled by the cross-source key above).
    stmt = (
        select(WorkoutCompleted)
        .where(WorkoutCompleted.deleted_at.is_(None))
        .where(WorkoutCompleted.athlete_id == athlete_id)
        .where(WorkoutCompleted.workout_date == workout_date)
        .where(WorkoutCompleted.source_file_id.is_(None))
    )
    res = await session.execute(stmt)
    existing_on_date = res.scalars().all()
    for ex in existing_on_date:
        ex_key = _within_csv_key(ex.workout_date, ex.duration_s, ex.distance_m, ex.name)
        if ex_key == within_key:
            return False

    from app.repositories.metrics_repo import FtpRepository
    from app.services.metrics import tss_calculator

    workout_repo = WorkoutRepository(session, ctx)
    ftp_repo = FtpRepository(session, ctx)
    ftp = await ftp_repo.value_on(workout_date, athlete_id)

    tss = act.source_tss
    intf = act.source_if
    np_value = None
    if act.avg_power and ftp and act.duration_s:
        np_value = act.source_np or act.avg_power
        intf = tss_calculator.intensity_factor(np_value, ftp) or intf
        tss = tss_calculator.tss_from_np(act.duration_s, np_value, ftp) or tss

    # Provenance: WorkoutCompleted has no source column, so we record the
    # source on the extra dict (CSV-summary rows have no source_file_id).
    extra = dict(act.extra) if act.extra else {}
    extra["source"] = source

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
        extra=extra,
        created_by=athlete_id,
    )
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

    # Provenance: WorkoutPlanned has no source column → record on extra.
    extra = dict(tp.extra) if tp.extra else {}
    extra["source"] = source

    row = WorkoutPlanned(
        athlete_id=athlete_id,
        planned_date=tp.planned_date,
        name=tp.name,
        workout_type=tp.workout_type,
        planned_duration_s=tp.planned_duration_s,
        planned_tss=tp.planned_tss,
        description=tp.description,
        extra=extra,
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
    - raw files: content-hash dedup via import_file
    - planned workouts: natural-key dedup by (athlete_id, planned_date, name)
    - completed CSV workouts: skipped if EITHER its cross-source key
      (workout_date, duration_bucket) matches an already-imported raw-file
      workout, OR its within-CSV key (workout_date, duration_bucket,
      distance_disc) matches an already-persisted CSV-derived workout

    See ``IngestionReport`` for report-field semantics (counts = created this
    run; period & coverage = over this run's parsed dataset, stable across runs).
    """
    report = IngestionReport()

    # Dates parsed out of the files (metrics + workouts), used to derive the
    # report period independently of whether rows were newly created.
    parsed_dates: list[date] = []
    # Parsed completed activities (NormalizedActivity) for stable coverage %.
    parsed_completed: list = []
    # Parsed recovery metrics (TpDailyMetric) for stable HRV coverage %.
    parsed_recovery: list = []

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
                    parsed_recovery.append(m)
                    parsed_dates.append(m.metric_date)
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

    # ------------------------------------------------------------------ #
    # 3. Raw activity files (import_file with content-hash dedup)          #
    # ------------------------------------------------------------------ #
    # Collect cross-source keys (date, duration_bucket) of imported raw-file
    # workouts, for CSV-vs-raw cross-dedup below (duration only, NO distance).
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

                if result.workouts_created > 0:
                    # Record cross-source keys of newly created workouts so a
                    # CSV summary for the same session (date+duration) dedups.
                    stmt = (
                        select(WorkoutCompleted)
                        .where(WorkoutCompleted.deleted_at.is_(None))
                        .where(WorkoutCompleted.athlete_id == athlete_id)
                        .where(WorkoutCompleted.source_file_id == result.imported_file.id)
                    )
                    res = await session.execute(stmt)
                    for w in res.scalars().all():
                        raw_file_keys.add(
                            _cross_source_key(w.workout_date, w.duration_s)
                        )

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
                    parsed_completed.append(act)
                    parsed_dates.append(act.started_at.date())
                    inserted = await _persist_completed_csv(
                        session, ctx, athlete_id, act, raw_file_keys, source
                    )
                    if inserted:
                        csv_completed_created += 1
                    else:
                        report.duplicates_skipped += 1

                for tp in planned_acts:
                    parsed_dates.append(tp.planned_date)
                    inserted = await _persist_planned(
                        session, ctx, athlete_id, tp, source
                    )
                    if inserted:
                        csv_planned_created += 1
                    else:
                        report.duplicates_skipped += 1

    # ------------------------------------------------------------------ #
    # 5. Finalise report                                                   #
    # ------------------------------------------------------------------ #
    # Counts mean "rows created THIS run".
    report.workouts_completed = raw_files_total_created + csv_completed_created
    report.workouts_planned = csv_planned_created

    # Period: derived from the dates PARSED OUT OF THE FILES (metrics + workouts),
    # independent of whether rows were newly created → stable across runs.
    if parsed_dates:
        report.period_start = min(parsed_dates)
        report.period_end = max(parsed_dates)

    # Coverage %: computed over THIS run's parsed dataset → stable & comparable.
    total_c = len(parsed_completed)
    if total_c:
        with_power = sum(1 for a in parsed_completed if a.avg_power is not None)
        with_hr = sum(1 for a in parsed_completed if a.avg_hr is not None)
        report.pct_power = 100.0 * with_power / total_c
        report.pct_hr = 100.0 * with_hr / total_c

    total_rec = len(parsed_recovery)
    if total_rec:
        with_hrv = sum(1 for r in parsed_recovery if r.hrv_ms is not None)
        report.pct_hrv = 100.0 * with_hrv / total_rec

    # Anomalies over the parsed completed dataset.
    report.anomalies = _detect_anomalies(parsed_completed)

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
