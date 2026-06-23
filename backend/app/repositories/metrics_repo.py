"""Repositories for load series, FTP history and recovery/subjective metrics."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select

from app.models.metrics import (
    FtpHistory,
    LoadMetric,
    RecoveryMetric,
    SubjectiveMetric,
)
from app.repositories.base import TenantRepository


class LoadMetricRepository(TenantRepository[LoadMetric]):
    model = LoadMetric

    async def list_between(
        self, start: date, end: date, athlete_id: uuid.UUID | None = None
    ) -> list[LoadMetric]:
        stmt = (
            self._base_select(athlete_id)
            .where(LoadMetric.metric_date >= start)
            .where(LoadMetric.metric_date <= end)
            .order_by(LoadMetric.metric_date)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_by_date(
        self, d: date, athlete_id: uuid.UUID | None = None
    ) -> LoadMetric | None:
        stmt = self._base_select(athlete_id).where(LoadMetric.metric_date == d)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def latest(self, athlete_id: uuid.UUID | None = None) -> LoadMetric | None:
        stmt = (
            self._base_select(athlete_id)
            .order_by(LoadMetric.metric_date.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()


class FtpRepository(TenantRepository[FtpHistory]):
    model = FtpHistory

    async def value_on(
        self, d: date, athlete_id: uuid.UUID | None = None
    ) -> float | None:
        """Return the FTP valid on date ``d`` (validity-range lookup)."""
        stmt = (
            self._base_select(athlete_id)
            .where(FtpHistory.valid_from <= d)
            .where((FtpHistory.valid_to.is_(None)) | (FtpHistory.valid_to >= d))
            .order_by(FtpHistory.valid_from.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        return row.ftp_watts if row else None


class RecoveryRepository(TenantRepository[RecoveryMetric]):
    model = RecoveryMetric

    async def list_recent(
        self, since: date, athlete_id: uuid.UUID | None = None
    ) -> list[RecoveryMetric]:
        stmt = (
            self._base_select(athlete_id)
            .where(RecoveryMetric.metric_date >= since)
            .order_by(RecoveryMetric.metric_date)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())


class SubjectiveRepository(TenantRepository[SubjectiveMetric]):
    model = SubjectiveMetric

    async def list_recent(
        self, since: date, athlete_id: uuid.UUID | None = None
    ) -> list[SubjectiveMetric]:
        stmt = (
            self._base_select(athlete_id)
            .where(SubjectiveMetric.metric_date >= since)
            .order_by(SubjectiveMetric.metric_date)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
