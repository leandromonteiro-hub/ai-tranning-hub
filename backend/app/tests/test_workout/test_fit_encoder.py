# backend/app/tests/test_workout/test_fit_encoder.py
import pytest

from app.services.workout.fit_encoder import encode
from app.services.workout.model import Repeat, Step, StructuredWorkout, Target


def _decode_steps(data: bytes):
    from fit_tool.fit_file import FitFile
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    steps = []
    for r in FitFile.from_bytes(data).records:
        if isinstance(r.message, WorkoutStepMessage):
            m = r.message
            steps.append((m.intensity, m.duration_value,
                          m.custom_target_power_low, m.custom_target_power_high,
                          m.target_type))
    return steps


def test_encode_flattens_repeats_and_encodes_watts():
    from fit_tool.profile.profile_type import WorkoutStepTarget
    w = StructuredWorkout(
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
            Step(intensity="cooldown", duration_s=600, target=Target(type="open")),
        ],
        ftp_watts=250.0,
    )
    data = encode(w)
    steps = _decode_steps(data)
    # 1 warmup + (2 steps * 3) + 1 cooldown = 8 flattened steps
    assert len(steps) == 8
    # warmup duration is in ms
    assert steps[0][1] == 600000
    # first active interval: 0.88*250=220W -> 1220, 0.93*250=232.5->round 233 -> 1233
    assert steps[1][0] == 0      # Intensity.ACTIVE == 0
    assert steps[1][2] == 1220
    assert steps[1][3] == 1233
    # rest step (index 2): intensity REST==1, duration 300s, power 0.50/0.55 of 250
    # floor(0.50*250+0.5)+1000=1125, floor(0.55*250+0.5)+1000=1138
    assert steps[2][0] == 1      # Intensity.REST == 1
    assert steps[2][1] == 300000
    assert steps[2][2] == 1125
    assert steps[2][3] == 1138
    # cooldown step (index 7): intensity COOLDOWN==3, target_type OPEN
    assert steps[7][0] == 3      # Intensity.COOLDOWN == 3
    assert steps[7][4] == WorkoutStepTarget.OPEN.value


def test_encode_requires_ftp():
    w = StructuredWorkout(name="x", elements=[
        Step(intensity="active", duration_s=600, target=Target(type="open"))])
    with pytest.raises(ValueError):
        encode(w)
