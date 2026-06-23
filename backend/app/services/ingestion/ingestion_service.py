"""Orchestrates file import: hash -> dedup -> parse -> validate -> compute -> persist.

Returns the ImportedFile row reflecting the outcome. Designed to be callable
both synchronously (small uploads in-request) and from a Celery job.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.models.enums import FileFormat, ImportStatus
from app.models.workout import ImportedFile, WorkoutCompleted, WorkoutStream
from app.repositories.metrics_repo import FtpRepository
from app.repositories.workout_repo import ImportedFileRepository, WorkoutRepository
from app.services.ingestion import (
    csv_importer,
    fit_importer,
    gpx_importer,
    tcx_importer,
)
from app.services.ingestion.deduplicator import content_hash
from app.services.ingestion.normalizer import NormalizedActivity
from app.services.ingestion.quality_validator import validate_activity
from app.services.metrics import tss_calculator

log = get_logger(__name__)

_PARSERS = {
    FileFormat.CSV: csv_importer.parse_csv,
    FileFormat.FIT: fit_importer.parse_fit,
    FileFormat.GPX: gpx_importer.parse_gpx,
    FileFormat.TCX: tcx_importer.parse_tcx,
}


@dataclass
class ImportResult:
    imported_file: ImportedFile
    workouts_created: int
    duplicates_skipped: int
    warnings: list[str]


def detect_format(filename: str) -> FileFormat | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mapping = {
        "csv": FileFormat.CSV,
        "fit": FileFormat.FIT,
        "gpx": FileFormat.GPX,
        "tcx": FileFormat.TCX,
        "json": FileFormat.JSON,
    }
    return mapping.get(ext)


async def import_file(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    filename: str,
    data: bytes,
    source: str | None = None,
) -> ImportResult:
    file_repo = ImportedFileRepository(session, ctx)
    workout_repo = WorkoutRepository(session, ctx)
    ftp_repo = FtpRepository(session, ctx)

    fmt = detect_format(filename)
    digest = content_hash(data)
    warnings: list[str] = []

    # 1. Deduplicate by content hash.
    existing = await file_repo.find_by_hash(digest, athlete_id)
    if existing:
        log.info("import_duplicate", extra={"hash": digest})
        record = ImportedFile(
            athlete_id=athlete_id,
            filename=filename,
            file_format=fmt or FileFormat.JSON,
            content_hash=digest,
            size_bytes=len(data),
            status=ImportStatus.DUPLICATE,
            source=source,
        )
        await file_repo.add(record)
        return ImportResult(record, 0, 1, ["duplicate file (same content hash)"])

    record = ImportedFile(
        athlete_id=athlete_id,
        filename=filename,
        file_format=fmt or FileFormat.JSON,
        content_hash=digest,
        size_bytes=len(data),
        status=ImportStatus.PROCESSING,
        source=source,
    )
    await file_repo.add(record)

    if fmt is None or fmt not in _PARSERS:
        record.status = ImportStatus.FAILED
        record.error_message = f"unsupported format: {filename}"
        return ImportResult(record, 0, 0, [record.error_message])

    # 2. Parse.
    try:
        activities = _PARSERS[fmt](data)
    except Exception as exc:  # noqa: BLE001 — record the failure, don't crash the request
        log.exception("import_parse_failed")
        record.status = ImportStatus.FAILED
        record.error_message = f"parse error: {exc}"
        return ImportResult(record, 0, 0, [record.error_message])

    created = 0
    duplicates = 0
    for act in activities:
        report = validate_activity(act)
        warnings.extend(report.warnings)
        if not report.is_valid:
            warnings.append(f"skipped invalid activity: {report.errors}")
            continue

        # 3. Cross-format dedup by external_id when present.
        if act.external_id:
            dup = await workout_repo.find_by_external_id(act.external_id, athlete_id)
            if dup:
                duplicates += 1
                continue

        workout = await _persist_activity(
            session, workout_repo, ftp_repo, athlete_id, act, record.id
        )
        if workout is not None:
            created += 1

    record.status = ImportStatus.COMPLETED
    record.rows_imported = created
    record.meta = {"warnings": warnings[:50], "duplicates": duplicates}
    log.info(
        "import_completed",
        extra={"workouts_created": created, "duplicates": duplicates, "file_format": fmt.value},
    )
    return ImportResult(record, created, duplicates, warnings)


async def _persist_activity(
    session: AsyncSession,
    workout_repo: WorkoutRepository,
    ftp_repo: FtpRepository,
    athlete_id: uuid.UUID,
    act: NormalizedActivity,
    file_id: uuid.UUID,
) -> WorkoutCompleted | None:
    workout_date = act.started_at.date()
    ftp = await ftp_repo.value_on(workout_date, athlete_id)

    # Recompute NP/IF/TSS from the power stream when available (measured data).
    np_value = None
    tss = act.source_tss
    intf = act.source_if
    kj = None
    if act.power_stream:
        np_value = tss_calculator.normalized_power(act.power_stream)
        intf = tss_calculator.intensity_factor(np_value, ftp) or intf
        tss = tss_calculator.tss_from_np(act.duration_s, np_value, ftp) or tss
        kj = tss_calculator.kilojoules(act.power_stream)
    elif act.avg_power and ftp and act.duration_s:
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
        elevation_gain_m=act.elevation_gain_m,
        avg_power=act.avg_power,
        normalized_power=np_value or act.source_np,
        avg_hr=act.avg_hr,
        max_hr=act.max_hr,
        avg_cadence=act.avg_cadence,
        kj=kj,
        intensity_factor=intf,
        tss=tss,
        ftp_used=ftp,
        source_file_id=file_id,
        external_id=act.external_id,
        notes=act.notes,
    )
    await workout_repo.add(workout)

    if act.power_stream or act.hr_stream:
        stream = WorkoutStream(
            athlete_id=athlete_id,
            workout_id=workout.id,
            power=act.power_stream or None,
            heart_rate=act.hr_stream or None,
            cadence=act.cadence_stream or None,
            altitude=act.altitude_stream or None,
        )
        session.add(stream)
        await session.flush()
    return workout
