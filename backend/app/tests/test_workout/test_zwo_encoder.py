"""Encode a StructuredWorkout to Zwift .zwo XML (TrainingPeaks-importable)."""
from __future__ import annotations

import xml.etree.ElementTree as ET

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
            Step(intensity="cooldown", duration_s=600, target=Target(type="open")),
        ],
        ftp_watts=250.0,
    )


def test_zwo_is_valid_xml_with_bike_sport_and_name():
    from app.services.workout.zwo_encoder import encode_zwo
    xml = encode_zwo(_sweet_spot())
    root = ET.fromstring(xml)  # raises if malformed
    assert root.tag == "workout_file"
    assert root.findtext("sportType") == "bike"
    assert root.findtext("name") == "Sweet Spot 3x12"
    assert root.find("workout") is not None


def test_repeat_becomes_native_intervalst_not_flattened():
    from app.services.workout.zwo_encoder import encode_zwo
    root = ET.fromstring(encode_zwo(_sweet_spot()))
    intervals = root.find("workout").findall("IntervalsT")
    assert len(intervals) == 1
    iv = intervals[0]
    assert iv.get("Repeat") == "3"
    assert iv.get("OnDuration") == "720"
    assert iv.get("OffDuration") == "300"
    # OnPower is the midpoint of 0.88..0.93 = 0.905
    assert abs(float(iv.get("OnPower")) - 0.905) < 1e-6
    assert abs(float(iv.get("OffPower")) - 0.525) < 1e-6


def test_warmup_is_ramp_and_open_cooldown_is_freeride():
    from app.services.workout.zwo_encoder import encode_zwo
    wk = root = ET.fromstring(encode_zwo(_sweet_spot())).find("workout")
    warm = wk.find("Warmup")
    assert warm is not None
    assert warm.get("Duration") == "600"
    assert abs(float(warm.get("PowerLow")) - 0.55) < 1e-6
    assert abs(float(warm.get("PowerHigh")) - 0.65) < 1e-6
    # open target (cooldown) -> FreeRide (no power)
    fr = wk.find("FreeRide")
    assert fr is not None and fr.get("Duration") == "600"


def test_steady_state_uses_single_midpoint_power():
    from app.services.workout.zwo_encoder import encode_zwo
    w = StructuredWorkout(
        name="Endurance",
        elements=[Step(intensity="active", duration_s=3600,
                       target=Target(type="power_pct_ftp", low=0.62, high=0.68))],
    )
    wk = ET.fromstring(encode_zwo(w)).find("workout")
    ss = wk.find("SteadyState")
    assert ss is not None and ss.get("Duration") == "3600"
    assert abs(float(ss.get("Power")) - 0.65) < 1e-6
