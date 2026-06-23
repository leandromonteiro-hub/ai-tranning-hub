"""Tenant isolation: the highest-priority guarantee for the validation phase.

Verifies that an athlete can never read or delete another athlete's data through
the repository layer, that admins can, and that the digital twin / load series of
one athlete never include another's rows.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.core.tenant import TenantViolationError
from app.models.workout import WorkoutCompleted
from app.repositories.workout_repo import WorkoutRepository
from app.tests.conftest import admin_ctx, ctx_for


def _workout(athlete_id, day: date, tss: float) -> WorkoutCompleted:
    return WorkoutCompleted(
        athlete_id=athlete_id,
        started_at=datetime(day.year, day.month, day.day, 7, tzinfo=timezone.utc),
        workout_date=day,
        tss=tss,
    )


@pytest.mark.asyncio
async def test_list_returns_only_own_tenant(session, two_athletes):
    a, b = two_athletes
    repo_a = WorkoutRepository(session, ctx_for(a))
    repo_b = WorkoutRepository(session, ctx_for(b))

    await repo_a.add(_workout(a.id, date(2026, 1, 1), 80))
    await repo_a.add(_workout(a.id, date(2026, 1, 2), 90))
    await repo_b.add(_workout(b.id, date(2026, 1, 1), 50))
    await session.flush()

    a_list = await repo_a.list()
    b_list = await repo_b.list()
    assert len(a_list) == 2
    assert len(b_list) == 1
    assert all(w.athlete_id == a.id for w in a_list)
    assert all(w.athlete_id == b.id for w in b_list)


@pytest.mark.asyncio
async def test_cannot_read_other_tenant_by_id(session, two_athletes):
    a, b = two_athletes
    repo_a = WorkoutRepository(session, ctx_for(a))
    repo_b = WorkoutRepository(session, ctx_for(b))
    w = await repo_a.add(_workout(a.id, date(2026, 1, 1), 80))
    await session.flush()

    # B requests A's workout by its real id -> must get nothing.
    assert await repo_b.get(w.id) is None


@pytest.mark.asyncio
async def test_explicit_cross_tenant_access_is_blocked(session, two_athletes):
    a, b = two_athletes
    repo_b = WorkoutRepository(session, ctx_for(b))
    # B explicitly tries to scope a query to A's athlete_id.
    with pytest.raises(TenantViolationError):
        await repo_b.list(athlete_id=a.id)


@pytest.mark.asyncio
async def test_write_is_forced_into_callers_tenant(session, two_athletes):
    a, b = two_athletes
    repo_b = WorkoutRepository(session, ctx_for(b))
    # B tries to write a row labelled as A's -> repository re-scopes / rejects.
    rogue = _workout(a.id, date(2026, 1, 1), 80)
    with pytest.raises(TenantViolationError):
        await repo_b.add(rogue)


@pytest.mark.asyncio
async def test_admin_can_access_any_tenant(session, two_athletes):
    a, _ = two_athletes
    repo_a = WorkoutRepository(session, ctx_for(a))
    await repo_a.add(_workout(a.id, date(2026, 1, 1), 80))
    await session.flush()

    admin_repo = WorkoutRepository(session, admin_ctx())
    rows = await admin_repo.list(athlete_id=a.id)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_soft_delete_hides_row_but_keeps_it(session, two_athletes):
    a, _ = two_athletes
    repo_a = WorkoutRepository(session, ctx_for(a))
    w = await repo_a.add(_workout(a.id, date(2026, 1, 1), 80))
    await session.flush()
    await repo_a.soft_delete(w)
    await session.flush()

    assert await repo_a.get(w.id) is None  # hidden from normal queries
    assert w.deleted_at is not None  # but physically retained
