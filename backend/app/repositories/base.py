"""Tenant-aware repository base.

Every athlete-scoped read/write goes through here. The repository ALWAYS adds
two predicates to queries on tenant models:

  * ``deleted_at IS NULL``        (soft-delete filter)
  * ``athlete_id == ctx.athlete_id``  (tenant isolation)

Non-admin principals can never widen the athlete_id filter. Admins may pass an
explicit ``athlete_id`` to operate cross-tenant, which is the only supported way
to do so and is expected to be audited by the caller.
"""
from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext, TenantViolationError
from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class TenantRepository(Generic[ModelT]):
    """Base repository scoped to a single tenant (athlete)."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession, ctx: TenantContext):
        self.session = session
        self.ctx = ctx

    # -- internal helpers -------------------------------------------------
    def _scoped_athlete_id(self, athlete_id: uuid.UUID | None) -> uuid.UUID:
        """Resolve and validate the athlete_id to operate on."""
        if athlete_id is None:
            return self.ctx.athlete_id
        # Non-admins may only ever touch their own tenant.
        self.ctx.assert_can_access(athlete_id)
        return athlete_id

    def _base_select(self, athlete_id: uuid.UUID | None = None):
        target = self._scoped_athlete_id(athlete_id)
        return (
            select(self.model)
            .where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
            .where(self.model.athlete_id == target)  # type: ignore[attr-defined]
        )

    # -- CRUD -------------------------------------------------------------
    async def list(self, athlete_id: uuid.UUID | None = None, limit: int = 200):
        stmt = self._base_select(athlete_id).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get(self, obj_id: uuid.UUID, athlete_id: uuid.UUID | None = None) -> ModelT | None:
        stmt = self._base_select(athlete_id).where(self.model.id == obj_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def add(self, obj: ModelT) -> ModelT:
        # Enforce tenant + provenance on write — never trust the caller blindly.
        target = self._scoped_athlete_id(getattr(obj, "athlete_id", None))
        obj.athlete_id = target  # type: ignore[attr-defined]
        if obj.created_by is None:
            obj.created_by = self.ctx.athlete_id
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def soft_delete(self, obj: ModelT) -> None:
        from datetime import datetime, timezone

        if getattr(obj, "athlete_id", None) is not None:
            self.ctx.assert_can_access(obj.athlete_id)  # type: ignore[attr-defined]
        obj.deleted_at = datetime.now(timezone.utc)
        self.session.add(obj)
        await self.session.flush()
