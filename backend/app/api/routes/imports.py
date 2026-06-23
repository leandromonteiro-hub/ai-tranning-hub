"""File upload + import endpoints (CSV/FIT/TCX/GPX), single and batch."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.schemas.workout import ImportedFileRead
from app.services.ingestion.ingestion_service import import_file
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
