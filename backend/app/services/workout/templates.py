"""Deterministic workout templates, parameterised by FTP.

Each template returns a StructuredWorkout with targets as fractions of FTP.
Zone anchors follow docs/training_methodology.md (Z1 recovery ~0.50-0.58,
Z2 endurance ~0.62-0.68, sweet spot ~0.88-0.93, VO2max ~1.10-1.18).
"""
from __future__ import annotations

from typing import Callable

from app.models.enums import BlockType, WorkoutType
from app.services.workout.model import Repeat, Step, StructuredWorkout, Target


def _pwr(low: float, high: float) -> Target:
    return Target(type="power_pct_ftp", low=low, high=high)


def _cooldown_target() -> Target:
    # A real (gentle ramp-down) target so the cooldown counts toward the planned
    # total duration in TrainingPeaks/.fit (an "open"/FreeRide cooldown is not counted).
    return _pwr(0.40, 0.50)


def recovery(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Recuperação Z1",
        elements=[Step(intensity="active", duration_s=2700, target=_pwr(0.50, 0.58))],
    )


def endurance(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Endurance Z2",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.60)),
            Step(intensity="active", duration_s=3600, target=_pwr(0.62, 0.68)),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def sweet_spot(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Sweet Spot 3x12",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.65)),
            Repeat(count=3, steps=[
                Step(intensity="active", duration_s=720, target=_pwr(0.88, 0.93)),
                Step(intensity="rest", duration_s=300, target=_pwr(0.50, 0.55)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def vo2max(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="VO2max 5x4",
        elements=[
            Step(intensity="warmup", duration_s=900, target=_pwr(0.55, 0.70)),
            Repeat(count=5, steps=[
                Step(intensity="active", duration_s=240, target=_pwr(1.10, 1.18)),
                Step(intensity="rest", duration_s=240, target=_pwr(0.45, 0.50)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def openers(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Openers 3x1",
        elements=[
            Step(intensity="warmup", duration_s=900, target=_pwr(0.55, 0.65)),
            Repeat(count=3, steps=[
                Step(intensity="active", duration_s=60, target=_pwr(1.05, 1.15)),
                Step(intensity="rest", duration_s=180, target=_pwr(0.50, 0.55)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def tempo(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Tempo 2x20",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.65)),
            Repeat(count=2, steps=[
                Step(intensity="active", duration_s=1200, target=_pwr(0.76, 0.85)),
                Step(intensity="rest", duration_s=300, target=_pwr(0.50, 0.55)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def forca_cadencia(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Força 4x8 (50-60 rpm)",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.65)),
            Repeat(count=4, steps=[
                Step(intensity="active", duration_s=480, target=_pwr(0.75, 0.85),
                     cadence_low=50, cadence_high=60,
                     note="Sentado, cadência 50-60 rpm"),
                Step(intensity="rest", duration_s=300, target=_pwr(0.50, 0.55)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def z2_sprints(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Z2 + 6 sprints",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.60)),
            Step(intensity="active", duration_s=1800, target=_pwr(0.62, 0.68)),
            Repeat(count=6, steps=[
                Step(intensity="active", duration_s=10, target=_pwr(1.50, 2.00),
                     note="Sprint sentado, cadência máxima"),
                Step(intensity="rest", duration_s=290, target=_pwr(0.60, 0.65)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def z2_progressivo(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Z2 progressivo",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.60)),
            Step(intensity="active", duration_s=1200, target=_pwr(0.60, 0.65)),
            Step(intensity="active", duration_s=1200, target=_pwr(0.65, 0.70)),
            Step(intensity="active", duration_s=1200, target=_pwr(0.70, 0.75)),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def long_ride(ftp_watts: float, duration_s: int = 10800) -> StructuredWorkout:
    active = max(3600, duration_s - 1200)
    return StructuredWorkout(
        name="Longão Z2",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.60)),
            Step(intensity="active", duration_s=active, target=_pwr(0.62, 0.68)),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def long_ride_tempo(ftp_watts: float, duration_s: int = 10800) -> StructuredWorkout:
    # 3 blocos de 15min Z3 com 5min Z2 entre eles; o resto é Z2 puro.
    tempo_total = 3 * 900 + 3 * 300
    z2 = max(1800, duration_s - 1200 - tempo_total)
    return StructuredWorkout(
        name="Longão com tempo 3x15",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.60)),
            Step(intensity="active", duration_s=z2 // 2, target=_pwr(0.62, 0.68)),
            Repeat(count=3, steps=[
                Step(intensity="active", duration_s=900, target=_pwr(0.78, 0.84)),
                Step(intensity="rest", duration_s=300, target=_pwr(0.62, 0.68)),
            ]),
            Step(intensity="active", duration_s=z2 - z2 // 2, target=_pwr(0.62, 0.68)),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


TEMPLATES: dict[BlockType, Callable[[float], StructuredWorkout]] = {
    BlockType.BASE: endurance,
    BlockType.BUILD: sweet_spot,
    BlockType.PEAK: vo2max,
    BlockType.TAPER: openers,
    BlockType.RECOVERY: recovery,
}

# Tipo de estímulo de cada bloco (paralelo a TEMPLATES). Usado para agregar
# feedback por tipo de treino. TAPER usa 'openers' (ativação) -> OTHER.
BLOCK_WORKOUT_TYPE: dict[BlockType, WorkoutType] = {
    BlockType.BASE: WorkoutType.ENDURANCE,
    BlockType.BUILD: WorkoutType.SWEET_SPOT,
    BlockType.PEAK: WorkoutType.VO2MAX,
    BlockType.TAPER: WorkoutType.OTHER,
    BlockType.RECOVERY: WorkoutType.RECOVERY,
}
