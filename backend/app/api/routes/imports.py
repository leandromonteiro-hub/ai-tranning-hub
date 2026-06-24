"""File upload + import endpoints (CSV/FIT/TCX/GPX), single and batch."""
from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.schemas.onboarding import (
    IngestionSummary,
    ProfileSummary,
    RichnessSummary,
    TrainingPeaksOnboardingResponse,
)
from app.schemas.workout import ImportedFileRead
from app.services.analysis.profile_service import generate_and_persist_profile
from app.services.ingestion.ingestion_service import import_file
from app.services.ingestion.tp_export_importer import import_athlete_folder
from app.services.metrics.recompute import recompute_load_metrics

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/upload", response_model=list[ImportedFileRead])
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
    for f in files:
        data = await f.read()
        result = await import_file(
            db, ctx, ctx.athlete_id, f.filename or "upload.bin", data, source=source
        )
        results.append(result.imported_file)

    if recompute:
        await recompute_load_metrics(db, ctx, ctx.athlete_id)

    return [ImportedFileRead.model_validate(r) for r in results]


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

    Processing steps (synchronous — validation scope, 2-athlete pilot):
    1. Stage each uploaded zip into a ``tempfile.TemporaryDirectory`` with its
       original filename so ``import_athlete_folder`` can classify by prefix.
    2. Call ``import_athlete_folder`` (Task-1 pipeline) — idempotent, multi-tenant
       scoped to ``ctx.athlete_id``.
    3. Call ``generate_and_persist_profile`` (Task-2 analysis) — idempotent,
       stores ``twin_seed`` + ``data_richness`` on ``AthleteProfile``.
    4. Commit the session.
    5. Return ingestion counts + data-richness index + profile summary.

    **Scalability note:** This endpoint is synchronous and suitable for small
    historical exports (validation scope: 2 athletes, typical TP exports <50 MB).
    For large batches, move to the async Celery path (see ``app.jobs.import_job``
    for the existing job pattern) — design-only, not yet wired up here.

    **Multi-tenant isolation:** all reads and writes are scoped to
    ``ctx.athlete_id``; one athlete's upload never touches another's rows.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Stage uploaded zips preserving original filenames so the orchestrator's
        # prefix classification (MetricsExport / WorkoutExport / WorkoutFileExport)
        # works correctly.
        for f in files:
            data = await f.read()
            dest = tmp_path / (f.filename or "upload.zip")
            dest.write_bytes(data)

        # Step 2: Run the Task-1 ingestion pipeline (idempotent).
        ingestion_report = await import_athlete_folder(
            db, ctx, ctx.athlete_id, tmp_path, source="trainingpeaks_export"
        )

    # Step 3: Run the Task-2 analysis pipeline (idempotent) — outside the
    # TemporaryDirectory context (tmp files no longer needed).
    profile_summary = await generate_and_persist_profile(db, ctx, ctx.athlete_id)

    # Step 4: Commit.
    await db.commit()

    # Step 5: Build and return the response.
    ingestion_dict = dataclasses.asdict(ingestion_report)
    richness_dict = profile_summary["richness"]

    return TrainingPeaksOnboardingResponse(
        ingestion=IngestionSummary(**ingestion_dict),
        richness=RichnessSummary(**richness_dict),
        profile=ProfileSummary(
            n_workouts=profile_summary["n_workouts"],
            weeks=profile_summary["weeks"],
            ftp_recent=profile_summary["ftp_recent"],
            n_blocks=profile_summary["n_blocks"],
            n_races=profile_summary["n_races"],
            excluded_power_streams=profile_summary["excluded_power_streams"],
            richness=richness_dict,
        ),
    )
