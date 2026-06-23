"""Encode a StructuredWorkout as a Garmin FIT workout file (power targets).

Repeats are flattened into sequential steps (robust thin-slice choice; native
repeat_until_steps_cmplt grouping is a future enhancement). FIT conventions
(validated by round-trip): duration in ms; custom power target = watts + 1000.
"""
from __future__ import annotations

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.workout_message import WorkoutMessage
from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
from fit_tool.profile.profile_type import (
    FileType, Intensity, Manufacturer, Sport, WorkoutStepDuration, WorkoutStepTarget,
)

from app.services.workout.model import Repeat, Step, StructuredWorkout

_INTENSITY = {
    "warmup": Intensity.WARMUP,
    "active": Intensity.ACTIVE,
    "rest": Intensity.REST,
    "cooldown": Intensity.COOLDOWN,
}


def _flatten(elements: list) -> list[Step]:
    out: list[Step] = []
    for el in elements:
        if isinstance(el, Repeat):
            for _ in range(el.count):
                out.extend(el.steps)
        else:
            out.append(el)
    return out


def _power_field(frac: float, ftp_watts: float) -> int:
    # Use arithmetic rounding (half-up) rather than Python's banker's rounding
    # to match FIT encoder convention: 0.93*250=232.5 -> 233, not 232.
    return int(frac * ftp_watts + 0.5) + 1000


def encode(workout: StructuredWorkout) -> bytes:
    if not workout.ftp_watts:
        raise ValueError("workout.ftp_watts is required to encode power targets")
    ftp = workout.ftp_watts
    steps = _flatten(workout.elements)

    builder = FitFileBuilder(auto_define=True)

    fid = FileIdMessage()
    fid.type = FileType.WORKOUT
    fid.manufacturer = Manufacturer.DEVELOPMENT.value
    fid.product = 0
    fid.serial_number = 1
    builder.add(fid)

    wm = WorkoutMessage()
    wm.workout_name = workout.name
    wm.sport = Sport.CYCLING
    wm.num_valid_steps = len(steps)
    builder.add(wm)

    for i, st in enumerate(steps):
        m = WorkoutStepMessage()
        m.message_index = i
        m.intensity = _INTENSITY[st.intensity]
        m.duration_type = WorkoutStepDuration.TIME
        m.duration_value = st.duration_s * 1000
        if st.target.type == "power_pct_ftp" and st.target.low is not None:
            high = st.target.high if st.target.high is not None else st.target.low
            m.target_type = WorkoutStepTarget.POWER
            m.custom_target_power_low = _power_field(st.target.low, ftp)
            m.custom_target_power_high = _power_field(high, ftp)
        else:
            m.target_type = WorkoutStepTarget.OPEN
        builder.add(m)

    return builder.build().to_bytes()
