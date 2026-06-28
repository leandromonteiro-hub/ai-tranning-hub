"""File upload + import endpoints (CSV/FIT/TCX/GPX), single and batch."""
from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.schemas.onboarding import (
    IngestionSummary,
    TrainingPeaksOnboardingResponse,
)
from app.jobs.profile_job import regenerate_profile_task
from app.schemas.workout import ImportedFileRead, UploadResponse
from app.services.ingestion.ingestion_service import import_file
from app.services.ingestion.tp_export_importer import import_athlete_folder
from app.services.metrics.recompute import recompute_load_metrics

router = APIRouter(prefix="/imports", tags=["imports"])
log = get_logger(__name__)


@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
    source: str | None = Query(default="manual"),
    recompute: bool = Query(default=True),
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Upload one or many activity files. Duplicates are detected and skipped.

    Small uploads are processed inline; large historical batches should use the
    async Celery import job (see app.jobs.import_job).
    """
    results = []
    workouts_created = 0
    for f in files:
        data = await f.read()
        result = await import_file(
            db, ctx, ctx.athlete_id, f.filename or "upload.bin", data, source=source
        )
        results.append(result.imported_file)
        workouts_created += result.workouts_created

    profile_task_id: str | None = None
    if recompute:
        # PMC (load metrics) stays inline — it's light. Only the heavy profile
        # regeneration (twin_seed / FTP / power curve) is offloaded to the worker.
        await recompute_load_metrics(db, ctx, ctx.athlete_id)
        await db.commit()
        if workouts_created > 0:
            # Enqueue is best-effort: a broker outage must never fail the import.
            try:
                task = regenerate_profile_task.delay(str(ctx.athlete_id), ctx.tenant_id)
                profile_task_id = task.id
            except Exception:
                log.exception("profile regen enqueue failed; import kept")

    return UploadResponse(
        files=[ImportedFileRead.model_validate(r) for r in results],
        profile_task_id=profile_task_id,
    )


@router.post("/trainingpeaks-export", response_model=TrainingPeaksOnboardingResponse)
async def onboard_trainingpeaks_export(
    files: list[UploadFile] = File(...),
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a TrainingPeaks export bundle and generate the athlete's profile.

    Accepts up to three export zip files (any combination):
    - ``MetricsExport-*.zip``     — daily HRV / sleep / resting-HR metrics
    - ``WorkoutExport-*.zip``     — completed + planned workouts (CSV wide format)
    - ``WorkoutFileExport-*.zip`` — raw activity files (.fit.gz / .tcx.gz / .gpx.gz)

    The filenames MUST be preserved so the orchestrator can classify each zip by
    its prefix (case-insensitive: MetricsExport / WorkoutExport / WorkoutFileExport).

    Processing steps:
    1. Stage each uploaded zip into a ``tempfile.TemporaryDirectory`` with its
       original filename so ``import_athlete_folder`` can classify by prefix.
    2. Call ``import_athlete_folder`` (Task-1 pipeline) — idempotent, multi-tenant
       scoped to ``ctx.athlete_id``. Ingestion runs INLINE.
    3. Commit the ingestion so the async worker's own session can see it.
    4. Enqueue the heavy profile regeneration (``regenerate_profile_task``) on the
       Celery worker — best-effort; a broker outage never fails the ingestion.
    5. Return ingestion counts + ``profile_task_id``. The profile (twin_seed /
       data_richness) is produced ASYNC; the client polls ``GET /jobs/{id}`` and
       fetches it via ``/athletes/me/intelligence`` on SUCCESS.

    **Multi-tenant isolation:** all reads and writes are scoped to
    ``ctx.athlete_id``; one athlete's upload never touches another's rows.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Stage uploaded zips preserving the original filename's BASENAME so the
        # orchestrator's prefix classification (MetricsExport / WorkoutExport /
        # WorkoutFileExport) works. Using only the basename (``Path(...).name``)
        # strips any directory components — a client-supplied ``../`` or absolute
        # path cannot escape the temp dir (path-traversal / arbitrary-file-write).
        for f in files:
            data = await f.read()
            safe_name = Path(f.filename or "upload.zip").name
            if not safe_name:
                # Filename was empty or all directory separators — skip.
                continue
            dest = tmp_path / safe_name
            dest.write_bytes(data)

        # Step 2: Run the Task-1 ingestion pipeline (idempotent).
        ingestion_report = await import_athlete_folder(
            db, ctx, ctx.athlete_id, tmp_path, source="trainingpeaks_export"
        )

    # Step 3: Commit the ingestion so the async worker (its own session) sees it.
    await db.commit()

    # Step 4: Enqueue the heavy profile regeneration (best-effort). A broker
    # outage must never fail the onboarding ingestion that already committed.
    profile_task_id = None
    try:
        task = regenerate_profile_task.delay(str(ctx.athlete_id), ctx.tenant_id)
        profile_task_id = task.id
    except Exception:
        log.exception("profile regen enqueue failed; onboarding ingestion kept")

    # Step 5: Build and return the response (profile arrives async).
    ingestion_dict = dataclasses.asdict(ingestion_report)
    return TrainingPeaksOnboardingResponse(
        ingestion=IngestionSummary(**ingestion_dict),
        profile_task_id=profile_task_id,
    )
