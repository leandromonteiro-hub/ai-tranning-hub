"""find_by_hash tolera hashes duplicados (dedup só precisa de UMA correspondência).

Regressão de produção (2026-07-08): o dedup insere uma linha status=DUPLICATE a
cada reencontro da mesma atividade, então o mesmo content_hash acumula 2+ linhas.
find_by_hash usava scalar_one_or_none() e estourava MultipleResultsFound,
derrubando TODO o sync do Garmin.
"""
from __future__ import annotations

import pytest

from app.models.enums import FileFormat, ImportStatus
from app.models.workout import ImportedFile
from app.repositories.workout_repo import ImportedFileRepository
from app.tests.conftest import ctx_for

_HASH = "a" * 64


def _imported(athlete_id, status=ImportStatus.COMPLETED) -> ImportedFile:
    return ImportedFile(
        athlete_id=athlete_id,
        filename="ride.fit",
        file_format=FileFormat.FIT,
        content_hash=_HASH,
        size_bytes=100,
        status=status,
        source="garmin",
    )


@pytest.mark.asyncio
async def test_find_by_hash_tolerates_duplicates(session, two_athletes):
    a, _ = two_athletes
    session.add_all([_imported(a.id), _imported(a.id, ImportStatus.DUPLICATE)])
    await session.flush()

    repo = ImportedFileRepository(session, ctx_for(a))
    # Não deve estourar MultipleResultsFound; retorna UMA correspondência.
    found = await repo.find_by_hash(_HASH, a.id)
    assert found is not None
    assert found.content_hash == _HASH


@pytest.mark.asyncio
async def test_find_by_hash_none_when_absent(session, two_athletes):
    a, _ = two_athletes
    repo = ImportedFileRepository(session, ctx_for(a))
    assert await repo.find_by_hash("b" * 64, a.id) is None
