from datetime import date

from app.models.athlete import AthleteProfile
from app.services.ai.profile_context import (
    anamnese_complete,
    profile_summary,
    twin_seed_summary,
)

_TWIN = {
    "intensity_split": {"label": "pyramidal", "z1_pct": 0.70, "z2_pct": 0.27, "z3_pct": 0.03},
    "power_curve_bests": {"5 s": 1227.0, "20 min": 331.0},
    "block_summary": [
        {"block_type": "build"}, {"block_type": "build"}, {"block_type": "recovery"},
    ],
    "data_richness": {"label": "alta", "score": 0.91},
}


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


def test_twin_seed_summary_surfaces_methodology():
    p = _full()
    p.twin_seed = _TWIN
    s = twin_seed_summary(p)
    assert "pyramidal" in s
    assert "Z1 70%" in s and "Z2 27%" in s and "Z3 3%" in s
    assert "1227W" in s and "331W" in s
    assert "3 blocos" in s and "2× build" in s   # periodization pattern
    assert "0.91" in s


def test_twin_seed_summary_nd_when_missing():
    assert twin_seed_summary(None) == "n/d"
    p = _full()  # profile without twin_seed
    assert twin_seed_summary(p) == "n/d"
