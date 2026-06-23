"""First-run bootstrap: ensure the admin account exists and pgvector is enabled."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.athlete import Athlete
from app.models.enums import Role
from app.repositories.athlete_repo import AthleteRepository

log = get_logger(__name__)


async def ensure_pgvector() -> None:
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await session.commit()
        except Exception:  # noqa: BLE001
            log.warning("pgvector_extension_not_available")


async def ensure_admin() -> None:
    async with AsyncSessionLocal() as session:
        repo = AthleteRepository(session)
        existing = await repo.get_by_email(settings.bootstrap_admin_email)
        if existing:
            return
        admin = Athlete(
            email=settings.bootstrap_admin_email,
            hashed_password=hash_password(settings.bootstrap_admin_password),
            full_name="System Admin",
            role=Role.ADMIN,
            tenant_id=f"tenant_admin_{uuid.uuid4().hex[:8]}",
        )
        await repo.add(admin)
        await session.commit()
        log.info("bootstrap_admin_created", extra={"email": settings.bootstrap_admin_email})


async def ensure_prompt_templates() -> None:
    """Persist the active prompt templates so recommendations can reference them."""
    from app.services.ai.prompt_store import ensure_templates

    async with AsyncSessionLocal() as session:
        try:
            await ensure_templates(session)
            await session.commit()
        except Exception:  # noqa: BLE001 — never block startup on this
            log.warning("prompt_template_seed_failed")
