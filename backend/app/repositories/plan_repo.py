"""Repository for training-plan reads (tenant-isolated)."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.models.enums import BlockType
from app.models.training_plan import TrainingWeek
from app.repositories.base import TenantRepository


class TrainingWeekRepository(TenantRepository[TrainingWeek]):
    model = TrainingWeek

    async def block_on(
        self, d: date, athlete_id: uuid.UUID | None = None
    ) -> BlockType | None:
        """Block type of the plan week covering date ``d``, else None."""
        stmt = (
            self._base_select(athlete_id)
            .where(TrainingWeek.week_start <= d)
            .order_by(TrainingWeek.week_start.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        week = res.scalar_one_or_none()
        if week and (d - week.week_start) < timedelta(days=7):
            return week.block_type
        return None
