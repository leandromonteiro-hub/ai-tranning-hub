"""DTO shape test: _build_garmin_workout_dict produces the correct Garmin schema.

Uses the garminconnect typed builders (workout.py).  The key invariant that the
old hand-built translator violated was the absence of numeric *Id fields
(sportTypeId, stepTypeId, conditionTypeId, workoutTargetTypeId).  These tests
guard against that regression.
"""
from __future__ import annotations

from app.services.garmin.client import _build_garmin_workout_dict
from app.services.workout.model import Repeat, Step, StructuredWorkout, Target


def _sw() -> StructuredWorkout:
    return StructuredWorkout(
        name="Intervals Test",
        ftp_watts=250.0,
        elements=[
            Step(
                intensity="warmup",
                duration_s=600,
                target=Target(type="power_pct_ftp", low=0.5, high=0.7),
            ),
            Repeat(
                count=4,
                steps=[
                    Step(
                        intensity="active",
                        duration_s=240,
                        target=Target(type="power_pct_ftp", low=1.1, high=1.2),
                    ),
                    Step(
                        intensity="rest",
                        duration_s=240,
                        target=Target(type="power_pct_ftp", low=0.5, high=0.5),
                    ),
                ],
            ),
            Step(intensity="cooldown", duration_s=300, target=Target(type="open")),
        ],
    )


def test_top_level_sport_type_has_numeric_id():
    d = _build_garmin_workout_dict(_sw())
    assert d["workoutName"] == "Intervals Test"
    assert d["sportType"]["sportTypeId"] == 2  # SportType.CYCLING
    assert d["sportType"]["sportTypeKey"] == "cycling"


def test_workout_segments_non_empty():
    d = _build_garmin_workout_dict(_sw())
    steps = d["workoutSegments"][0]["workoutSteps"]
    assert len(steps) == 3  # warmup + repeat-group + cooldown


def test_warmup_step_has_numeric_ids_and_duration():
    d = _build_garmin_workout_dict(_sw())
    warmup = d["workoutSegments"][0]["workoutSteps"][0]
    assert warmup["stepType"]["stepTypeId"] == 1   # StepType.WARMUP
    assert warmup["stepType"]["stepTypeKey"] == "warmup"
    assert warmup["endCondition"]["conditionTypeId"] == 2  # ConditionType.TIME
    assert warmup["endConditionValue"] == 600


def test_power_step_has_target_type_id_and_watts():
    d = _build_garmin_workout_dict(_sw())
    warmup = d["workoutSegments"][0]["workoutSteps"][0]
    # warmup has power target 0.5-0.7 x 250 = 125-175 W
    assert warmup["targetType"]["workoutTargetTypeId"] == 2  # TargetType.POWER_ZONE
    assert warmup["targetValueOne"] == 125
    assert warmup["targetValueTwo"] == 175


def test_repeat_has_correct_iterations_and_child_count():
    d = _build_garmin_workout_dict(_sw())
    repeat = d["workoutSegments"][0]["workoutSteps"][1]
    assert repeat["stepType"]["stepTypeId"] == 6  # StepType.REPEAT
    assert repeat["numberOfIterations"] == 4
    assert len(repeat["workoutSteps"]) == 2


def test_open_target_step_has_no_target_id():
    d = _build_garmin_workout_dict(_sw())
    cooldown = d["workoutSegments"][0]["workoutSteps"][2]
    assert cooldown["targetType"]["workoutTargetTypeId"] == 1  # TargetType.NO_TARGET
    assert "targetValueOne" not in cooldown
    assert "targetValueTwo" not in cooldown
