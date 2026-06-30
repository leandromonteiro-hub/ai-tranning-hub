"""Translate the canonical StructuredWorkout into Garmin Connect's workout dict.

Garmin's workout API expects absolute watts, so %FTP fractions are resolved via
``sw.ftp_watts``. Repeats map to a RepeatGroupDTO (no flattening). This dict is
what RealGarminClient.push_workout uploads."""
from __future__ import annotations

from app.services.workout.model import Repeat, Step, StructuredWorkout, Target

_INTENSITY_KEY = {
    "warmup": "warmup",
    "active": "interval",
    "rest": "recovery",
    "cooldown": "cooldown",
}


def _watts(target: Target, ftp: float | None) -> tuple[int | None, int | None]:
    if target.type != "power_pct_ftp" or target.low is None or ftp is None:
        return None, None
    high = target.high if target.high is not None else target.low
    return round(target.low * ftp), round(high * ftp)


def _step_dto(step: Step, ftp: float | None, order: int) -> dict:
    low, high = _watts(step.target, ftp)
    dto: dict = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeKey": _INTENSITY_KEY[step.intensity]},
        "endCondition": {"conditionTypeKey": "time"},
        "endConditionValue": step.duration_s,
    }
    if low is None:
        dto["targetType"] = {"workoutTargetTypeKey": "no.target"}
    else:
        dto["targetType"] = {"workoutTargetTypeKey": "power.zone"}
        dto["targetValueOne"] = low
        dto["targetValueTwo"] = high
    return dto


def to_garmin_workout(sw: StructuredWorkout) -> dict:
    ftp = sw.ftp_watts
    steps: list[dict] = []
    order = 1
    for el in sw.elements:
        if isinstance(el, Repeat):
            children = []
            for child in el.steps:
                children.append(_step_dto(child, ftp, order))
                order += 1
            steps.append({
                "type": "RepeatGroupDTO",
                "stepType": {"stepTypeKey": "repeat"},
                "numberOfIterations": el.count,
                "workoutSteps": children,
            })
        else:  # Step
            steps.append(_step_dto(el, ftp, order))
            order += 1
    return {
        "workoutName": sw.name,
        "sportType": {"sportTypeKey": "cycling"},
        "workoutSegments": [
            {"segmentOrder": 1,
             "sportType": {"sportTypeKey": "cycling"},
             "workoutSteps": steps},
        ],
    }
