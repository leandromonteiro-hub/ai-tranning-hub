"""Async import job for large historical batches."""
from __future__ import annotations

import uuid

from app.core.database import AsyncSessionLocal
from app.core.tenant import TenantContext
from app.jobs._run import run_async
from app.models.enums import Role
from app.services.ingestion.ingestion_service import import_file
from app.services.metrics.recompute import recompute_load_metrics


async def _do_import(
    athlete_id: str, tenant_id: str, filename: str, data: bytes, source: str | None
) -> dict:
    aid = uuid.UUID(athlete_id)
    ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)
    async with AsyncSessionLocal() as session:
        result = await import_file(session, ctx, aid, filename, data, source=source)
        await recompute_load_metrics(session, ctx, aid)
        await session.commit()
        return {
            "imported_file_id": str(result.imported_file.id),
            "workouts_created": result.workouts_created,
            "duplicates_skipped": result.duplicates_skipped,
            "status": result.imported_file.status.value,
        }


def import_file_task(
    athlete_id: str, tenant_id: str, filename: str, data: bytes, source: str | None = "manual"
) -> dict:
    return run_async(_do_import(athlete_id, tenant_id, filename, data, source))


# Register with Celery when the app is available.
try:
    from app.jobs.celery_app import celery

    import_file_task = celery.task(name="import_file")(import_file_task)  # type: ignore[assignment]
except Exception:  # noqa: BLE001 — importable without a running broker (e.g. tests)
    pass
