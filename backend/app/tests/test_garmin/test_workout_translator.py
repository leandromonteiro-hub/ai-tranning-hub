"""Tradução do modelo canônico para o dict de workout do Garmin."""
from __future__ import annotations

from app.services.garmin.workout_translator import to_garmin_workout
from app.services.workout.model import Repeat, Step, StructuredWorkout, Target


def _sw() -> StructuredWorkout:
    return StructuredWorkout(
        name="VO2 4x4",
        ftp_watts=250.0,
        elements=[
            Step(intensity="warmup", duration_s=600,
                 target=Target(type="power_pct_ftp", low=0.5, high=0.7)),
            Repeat(count=4, steps=[
                Step(intensity="active", duration_s=240,
                     target=Target(type="power_pct_ftp", low=1.1, high=1.2)),
                Step(intensity="rest", duration_s=240,
                     target=Target(type="power_pct_ftp", low=0.5, high=0.5)),
            ]),
            Step(intensity="cooldown", duration_s=300, target=Target(type="open")),
        ],
    )


def test_basic_shape():
    g = to_garmin_workout(_sw())
    assert g["workoutName"] == "VO2 4x4"
    assert g["sportType"]["sportTypeKey"] == "cycling"
    steps = g["workoutSegments"][0]["workoutSteps"]
    # warmup + repeat-group + cooldown = 3 top-level steps
    assert len(steps) == 3


def test_power_resolved_to_watts():
    g = to_garmin_workout(_sw())
    steps = g["workoutSegments"][0]["workoutSteps"]
    warmup = steps[0]
    # 0.5..0.7 * 250 = 125..175 W
    assert warmup["targetValueOne"] == 125
    assert warmup["targetValueTwo"] == 175


def test_repeat_group_has_children():
    g = to_garmin_workout(_sw())
    repeat = g["workoutSegments"][0]["workoutSteps"][1]
    assert repeat["type"] == "RepeatGroupDTO"
    assert repeat["numberOfIterations"] == 4
    assert len(repeat["workoutSteps"]) == 2


def test_open_target_has_no_power():
    g = to_garmin_workout(_sw())
    cooldown = g["workoutSegments"][0]["workoutSteps"][2]
    assert cooldown.get("targetType", {}).get("workoutTargetTypeKey") == "no.target"
