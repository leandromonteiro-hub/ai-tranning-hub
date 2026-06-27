import pytest

from app.models.enums import BlockType, RiskLevel
from app.services.workout.builder import build_for
from app.services.workout.model import Repeat


def _all_active_targets(w):
    out = []
    for el in w.elements:
        steps = el.steps if isinstance(el, Repeat) else [el]
        for s in steps:
            if s.intensity == "active" and s.target.low is not None:
                out.append(s.target.low)
    return out


def test_high_risk_always_recovery_regardless_of_block():
    for block in BlockType:
        w = build_for(block, RiskLevel.HIGH, 250.0)
        assert "recup" in w.name.lower() or "recovery" in w.name.lower()
        # recovery is easy: no active interval above 0.75 FTP
        assert all(t <= 0.75 for t in _all_active_targets(w))


def test_build_sets_ftp_and_low_risk_build_is_sweet_spot():
    w = build_for(BlockType.BUILD, RiskLevel.LOW, 250.0)
    assert w.ftp_watts == 250.0
    # sweet spot has a repeated active block around 0.88-0.93 FTP
    reps = [e for e in w.elements if isinstance(e, Repeat)]
    assert reps and reps[0].count == 3
    assert any(0.85 <= t <= 0.95 for t in _all_active_targets(w))


def test_moderate_reduces_volume_without_raising_intensity():
    low = build_for(BlockType.BUILD, RiskLevel.LOW, 250.0)
    mod = build_for(BlockType.BUILD, RiskLevel.MODERATE, 250.0)
    low_reps = [e for e in low.elements if isinstance(e, Repeat)][0].count
    mod_reps = [e for e in mod.elements if isinstance(e, Repeat)][0].count
    assert mod_reps < low_reps
    # intensity (peak active target) never exceeds the LOW version
    assert max(_all_active_targets(mod)) <= max(_all_active_targets(low))


from app.models.enums import WorkoutType
from app.services.workout.builder import workout_type_for


def test_workout_type_for_maps_each_block():
    assert workout_type_for(BlockType.BASE, RiskLevel.LOW) == WorkoutType.ENDURANCE
    assert workout_type_for(BlockType.BUILD, RiskLevel.LOW) == WorkoutType.SWEET_SPOT
    assert workout_type_for(BlockType.PEAK, RiskLevel.LOW) == WorkoutType.VO2MAX
    assert workout_type_for(BlockType.TAPER, RiskLevel.LOW) == WorkoutType.OTHER
    assert workout_type_for(BlockType.RECOVERY, RiskLevel.LOW) == WorkoutType.RECOVERY


def test_workout_type_for_high_risk_forces_recovery_over_block():
    for block in BlockType:
        assert workout_type_for(block, RiskLevel.HIGH) == WorkoutType.RECOVERY


def test_workout_type_for_moderate_keeps_block_type():
    # MODERATE reduz volume mas não muda o tipo de estímulo
    assert workout_type_for(BlockType.BUILD, RiskLevel.MODERATE) == WorkoutType.SWEET_SPOT
