"""generate_recommendation carrega os DOIS treinos no payload (comparativa)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.enums import BlockType
from app.models.workout import WorkoutCompleted
from app.services.ai.recommender import generate_recommendation
from app.services.workout import analysis as workout_analysis
from app.services.workout.model import StructuredWorkout
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


def _completed(athlete_id, day: date, duration_s: int) -> WorkoutCompleted:
    return WorkoutCompleted(
        athlete_id=athlete_id,
        started_at=datetime(day.year, day.month, day.day, 7, tzinfo=timezone.utc),
        workout_date=day,
        duration_s=duration_s,
    )


@pytest.mark.asyncio
async def test_methodology_workout_uses_median_of_in_window_durations(
    session, two_athletes, monkeypatch
):
    """The duration query must (a) actually be exercised (>=3 in-window rows,
    so the median path is taken instead of the block fallback) and (b) respect
    the upper bound at target_date — a future row with a wildly different
    duration must NOT influence the result."""
    a, _ = two_athletes
    ctx = ctx_for(a)
    target_date = date(2026, 7, 7)

    async def mock_value_on(self, d, aid):
        return 250.0

    async def mock_block_on(self, d, aid):
        return BlockType.BASE

    monkeypatch.setattr(
        "app.services.ai.recommender.FtpRepository.value_on", mock_value_on
    )
    monkeypatch.setattr(
        "app.services.ai.recommender.TrainingWeekRepository.block_on", mock_block_on
    )

    from app.models.athlete import AthleteProfile

    prof = AthleteProfile(
        athlete_id=a.id, birth_date=date(1990, 1, 1), sex="M", weight_kg=70,
        height_cm=175, max_hr=185, primary_discipline="XCM", years_training=5,
        goals="ultra", weekly_hours=10,
        twin_seed={"intensity_split": {"z1_pct": 0.68, "z2_pct": 0.29, "z3_pct": 0.03}},
    )
    session.add(prof)

    # In-window rows (within the last 90d, up to and including target_date):
    # median(3000, 6000, 9000) = 6000s — a distinctive value, far from the
    # block fallback (5400s) so the test fails if the fallback is used instead.
    session.add(_completed(a.id, target_date - timedelta(days=10), 3000))
    session.add(_completed(a.id, target_date - timedelta(days=5), 6000))
    session.add(_completed(a.id, target_date, 9000))
    # Out-of-window row AFTER target_date — must be excluded by the upper
    # bound; a wildly different duration would blow up the median if leaked.
    session.add(_completed(a.id, target_date + timedelta(days=3), 99999))
    await session.flush()

    rec = await generate_recommendation(session, ctx, a.id, target_date=target_date)

    mw = StructuredWorkout.model_validate(rec.payload["methodology_workout"])
    total_s = workout_analysis.total_duration_s(mw)

    # median = 6000s is the main-block "typical_s" input; warmup/cooldown
    # framing is added around it, so allow a small tolerance rather than
    # asserting exact equality.
    assert abs(total_s - 6000) < 120
    # Sanity: neither the block fallback (5400s) nor the excluded future
    # outlier (99999s) drove the result.
    assert abs(total_s - 5400) > 120


@pytest.mark.asyncio
async def test_default_texts_are_portuguese(session, two_athletes, monkeypatch):
    a, _ = two_athletes
    ctx = ctx_for(a)

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
    from app.models.athlete import AthleteProfile
    session.add(AthleteProfile(
        athlete_id=a.id, birth_date=date(1990, 1, 1), sex="M", weight_kg=70,
        height_cm=175, max_hr=185, primary_discipline="XCM", years_training=5,
        goals="ultra", weekly_hours=10,
    ))
    await session.flush()
    rec = await generate_recommendation(session, ctx, a.id, target_date=date(2026, 7, 7))
    # Sem palavras em inglês nos defaults; presença de acento/pt-BR.
    assert "stimulus" not in (rec.physiological_objective or "").lower()
    assert "if more fatigued" not in (rec.adjust_if_tired or "").lower()
    assert "if less time" not in (rec.adjust_if_less_time or "").lower()
    assert "Estímulo" in (rec.physiological_objective or "")
