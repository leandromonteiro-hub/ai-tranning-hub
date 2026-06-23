"""Async job: embed an athlete's recent content into the private vector space.

Produces ``embeddings`` rows with athlete_id set (never NULL), so athlete-private
vectors are isolated from the global knowledge base at query time. Idempotent per
(athlete_id, ref_table, ref_id): existing vectors for a row are not duplicated.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.jobs._run import run_async
from app.models.enums import Role
from app.models.knowledge import Embedding
from app.repositories.workout_repo import WorkoutRepository
from app.services.knowledge.embedder import embed_text

log = get_logger(__name__)


def _workout_sentence(w) -> str:
    parts = [f"Treino {w.workout_date} tipo {w.workout_type.value}"]
    if w.tss:
        parts.append(f"TSS {w.tss:.0f}")
    if w.normalized_power:
        parts.append(f"NP {w.normalized_power:.0f}W")
    if w.avg_hr:
        parts.append(f"FC media {w.avg_hr:.0f}")
    if w.duration_s:
        parts.append(f"duracao {w.duration_s // 60} min")
    if w.notes:
        parts.append(w.notes)
    return ", ".join(parts)


async def _embed_athlete_content(athlete_id: str, tenant_id: str, lookback_days: int) -> dict:
    aid = uuid.UUID(athlete_id)
    ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)
    created = 0
    async with AsyncSessionLocal() as session:
        repo = WorkoutRepository(session, ctx)
        end = date.today()
        workouts = await repo.list_between(end - timedelta(days=lookback_days), end, aid)
        for w in workouts:
            exists = await session.execute(
                select(Embedding.id).where(
                    Embedding.athlete_id == aid,
                    Embedding.ref_table == "workouts_completed",
                    Embedding.ref_id == w.id,
                    Embedding.deleted_at.is_(None),
                )
            )
            if exists.scalar_one_or_none():
                continue
            text = _workout_sentence(w)
            session.add(
                Embedding(
                    athlete_id=aid, namespace="workout",
                    ref_table="workouts_completed", ref_id=w.id,
                    chunk_text=text, embedding=embed_text(text),
                )
            )
            created += 1
        await session.commit()
    log.info("athlete_content_embedded", extra={"athlete_id": athlete_id, "created": created})
    return {"embeddings_created": created}


def embed_athlete_content_task(athlete_id: str, tenant_id: str, lookback_days: int = 365) -> dict:
    return run_async(_embed_athlete_content(athlete_id, tenant_id, lookback_days))


try:
    from app.jobs.celery_app import celery

    embed_athlete_content_task = celery.task(name="embed_athlete_content")(  # type: ignore[assignment]
        embed_athlete_content_task
    )
except Exception:  # noqa: BLE001
    pass
