"""Repository for the single Garmin connection per athlete."""
from __future__ import annotations

import uuid

from app.models.garmin import GarminConnection
from app.repositories.base import TenantRepository


class GarminConnectionRepository(TenantRepository[GarminConnection]):
    model = GarminConnection

    async def get_for_athlete(
        self, athlete_id: uuid.UUID | None = None
    ) -> GarminConnection | None:
        stmt = self._base_select(athlete_id).limit(1)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_or_create(
        self, athlete_id: uuid.UUID | None = None
    ) -> GarminConnection:
        existing = await self.get_for_athlete(athlete_id)
        if existing:
            return existing
        conn = GarminConnection(athlete_id=self._scoped_athlete_id(athlete_id))
        return await self.add(conn)
