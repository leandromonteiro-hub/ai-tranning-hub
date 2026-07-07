"""generate_recommendation carrega os DOIS treinos no payload (comparativa)."""
from __future__ import annotations

from datetime import date

import pytest

from app.models.enums import BlockType
from app.services.ai.recommender import generate_recommendation
from app.tests.conftest import ctx_for


@pytest.mark.asyncio
async def test_payload_carries_both_workouts(session, two_athletes, monkeypatch):
    a, _ = two_athletes
    ctx = ctx_for(a)

    # FTP disponível + twin com intensity_split -> deve gerar os dois treinos.
    async def mock_value_on(self, d, aid):
        return 250.0
    async def mock_block_on(self, d, aid):
        return BlockType.BASE

    monkeypatch.setattr(
        "app.services.ai.recommender.FtpRepository.value_on",
        mock_value_on,
    )
    monkeypatch.setattr(
        "app.services.ai.recommender.TrainingWeekRepository.block_on",
        mock_block_on,
    )
    # profile com twin_seed
    from app.models.athlete import AthleteProfile
    prof = AthleteProfile(
        athlete_id=a.id, birth_date=date(1990, 1, 1), sex="M", weight_kg=70,
        height_cm=175, max_hr=185, primary_discipline="XCM", years_training=5,
        goals="ultra", weekly_hours=10,
        twin_seed={"intensity_split": {"z1_pct": 0.68, "z2_pct": 0.29, "z3_pct": 0.03}},
    )
    session.add(prof)
    await session.flush()

    rec = await generate_recommendation(session, ctx, a.id, target_date=date(2026, 7, 7))
    assert rec.payload.get("structured_workout") is not None
    assert rec.payload.get("methodology_workout") is not None
    assert isinstance(rec.payload.get("methodology_workout_description"), str)
    # Nome reflete o estilo do atleta (pirâmidal -> endurance).
    assert "padrão" in rec.payload["methodology_workout"]["name"].lower()
