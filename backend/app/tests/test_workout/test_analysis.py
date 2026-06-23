"""Workout analysis: total duration, IF, TSS, and human-readable description."""
from __future__ import annotations

from app.services.workout import analysis
from app.services.workout.model import Repeat, Step, StructuredWorkout, Target


def _sweet_spot() -> StructuredWorkout:
    return StructuredWorkout(
        name="Sweet Spot 3x12",
        elements=[
            Step(intensity="warmup", duration_s=600,
                 target=Target(type="power_pct_ftp", low=0.55, high=0.65)),
            Repeat(count=3, steps=[
                Step(intensity="active", duration_s=720,
                     target=Target(type="power_pct_ftp", low=0.88, high=0.93)),
                Step(intensity="rest", duration_s=300,
                     target=Target(type="power_pct_ftp", low=0.50, high=0.55)),
            ]),
            Step(intensity="cooldown", duration_s=600,
                 target=Target(type="power_pct_ftp", low=0.40, high=0.50)),
        ],
    )


def test_total_duration_includes_warmup_rests_and_cooldown():
    # 600 warmup + 3*(720 active + 300 rest) + 600 cooldown = 4260s = 71 min
    assert analysis.total_duration_s(_sweet_spot()) == 4260


def test_intensity_factor_is_fourth_power_weighted():
    # Hand-computed ~0.79 for this session (see analysis._frac midpoints)
    assert 0.74 <= analysis.intensity_factor(_sweet_spot()) <= 0.84


def test_estimated_tss_uses_duration_and_if():
    # TSS = hours * IF^2 * 100 ; ~71min @ IF~0.79 -> ~70-78
    tss = analysis.estimated_tss(_sweet_spot())
    assert 65 <= tss <= 82


def test_describe_lists_rest_times_total_if_and_tss():
    text = analysis.describe(_sweet_spot())
    assert "total 71min" in text
    assert "IF" in text and "TSS" in text
    assert "descanso" in text.lower()          # rest time explicitly described
    assert "3×" in text or "3x" in text         # interval grouping shown
    assert "Aquecimento" in text and "calma" in text.lower()
