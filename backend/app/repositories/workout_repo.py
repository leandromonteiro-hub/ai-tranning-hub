"""Workout and imported-file repositories."""
from __future__ import annotations

import uuid
from datetime import date

from app.models.workout import ImportedFile, WorkoutCompleted
from app.repositories.base import TenantRepository


class WorkoutRepository(TenantRepository[WorkoutCompleted]):
    model = WorkoutCompleted

    async def list_between(
        self, start: date, end: date, athlete_id: uuid.UUID | None = None
    ) -> list[WorkoutCompleted]:
        stmt = (
            self._base_select(athlete_id)
            .where(WorkoutCompleted.workout_date >= start)
            .where(WorkoutCompleted.workout_date <= end)
            .order_by(WorkoutCompleted.workout_date)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def find_by_external_id(
        self, external_id: str, athlete_id: uuid.UUID | None = None
    ) -> WorkoutCompleted | None:
        stmt = self._base_select(athlete_id).where(
            WorkoutCompleted.external_id == external_id
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()


class ImportedFileRepository(TenantRepository[ImportedFile]):
    model = ImportedFile

    async def find_by_hash(
        self, content_hash: str, athlete_id: uuid.UUID | None = None
    ) -> ImportedFile | None:
        # Dedup só precisa saber SE já existe um arquivo com este hash. O dedup
        # insere uma linha status=DUPLICATE a cada reencontro, então o mesmo hash
        # pode ter 2+ linhas — first() (não one_or_none) evita MultipleResultsFound
        # que derrubaria o sync inteiro.
        stmt = self._base_select(athlete_id).where(
            ImportedFile.content_hash == content_hash
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()
