"""Athlete repository — operates on the principal table itself.

The Athlete table is not TenantMixin-scoped (it *defines* the tenant), so this
repository does not extend TenantRepository; isolation for it is enforced by
role checks in the service/route layer.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete


class AthleteRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_email(self, email: str) -> Athlete | None:
        stmt = select(Athlete).where(
            Athlete.email == email, Athlete.deleted_at.is_(None)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get(self, athlete_id: uuid.UUID) -> Athlete | None:
        stmt = select(Athlete).where(
            Athlete.id == athlete_id, Athlete.deleted_at.is_(None)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_all(self) -> list[Athlete]:
        stmt = select(Athlete).where(Athlete.deleted_at.is_(None))
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def add(self, athlete: Athlete) -> Athlete:
        self.session.add(athlete)
        await self.session.flush()
        return athlete
