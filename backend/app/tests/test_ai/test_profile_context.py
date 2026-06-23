from datetime import date

from app.models.athlete import AthleteProfile
from app.services.ai.profile_context import anamnese_complete, profile_summary


def _full() -> AthleteProfile:
    return AthleteProfile(
        birth_date=date(1990, 5, 10), sex="M", weight_kg=72.0, height_cm=178.0,
        max_hr=188, resting_hr=52, primary_discipline="XCO", years_training=6,
        goals="Vencer a maratona", weekly_hours=8.0, weekly_days=4,
    )


def test_anamnese_complete_true_when_all_required_present():
    assert anamnese_complete(_full()) is True


def test_anamnese_incomplete_when_missing_required():
    p = _full()
    p.goals = None
    assert anamnese_complete(p) is False
    assert anamnese_complete(None) is False


def test_profile_summary_includes_key_fields():
    s = profile_summary(_full())
    assert "Vencer a maratona" in s
    assert "XCO" in s
    assert "72" in s and "188" in s


def test_profile_summary_none_is_nd():
    assert profile_summary(None) == "n/d"
