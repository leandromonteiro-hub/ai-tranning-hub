"""Select and build a structured workout from the day's training intent.

The intent is the SAME (block_type, risk_level) the guardrails already produce,
so the structured workout inherits the safety posture: HIGH risk -> recovery,
MODERATE -> the block template with reduced volume (never higher intensity).
"""
from __future__ import annotations

from app.models.enums import BlockType, RiskLevel, WorkoutType
from app.services.workout import analysis, templates
from app.services.workout.templates import BLOCK_WORKOUT_TYPE
from app.services.workout.model import Repeat, StructuredWorkout


def _reduce(workout: StructuredWorkout) -> StructuredWorkout:
    """MODERATE risk: drop one repetition from each repeated block (min 1)."""
    new_elements = []
    for el in workout.elements:
        if isinstance(el, Repeat):
            new_elements.append(Repeat(count=max(1, el.count - 1), steps=el.steps))
        else:
            new_elements.append(el)
    return StructuredWorkout(
        name=workout.name + " (reduzido)",
        sport=workout.sport,
        elements=new_elements,
        ftp_watts=workout.ftp_watts,
    )


def build_for(
    block_type: BlockType, risk_level: RiskLevel, ftp_watts: float
) -> StructuredWorkout:
    if risk_level == RiskLevel.HIGH:
        workout = templates.recovery(ftp_watts)
    else:
        template_fn = templates.TEMPLATES.get(block_type, templates.endurance)
        workout = template_fn(ftp_watts)
        if risk_level == RiskLevel.MODERATE:
            workout = _reduce(workout)
    workout.ftp_watts = ftp_watts
    workout.estimated_tss = analysis.estimated_tss(workout)
    return workout


def workout_type_for(block_type: BlockType, risk_level: RiskLevel) -> WorkoutType:
    """Tipo de estímulo do treino diário, derivado de bloco+risco.

    Espelha a seleção de template de build_for: risco HIGH força RECOVERY
    (mesmo override que troca o template para `recovery`); caso contrário o
    tipo segue o bloco. Bloco desconhecido cai em ENDURANCE (default seguro,
    igual ao TEMPLATES.get(..., endurance))."""
    if risk_level == RiskLevel.HIGH:
        return WorkoutType.RECOVERY
    return BLOCK_WORKOUT_TYPE.get(block_type, WorkoutType.ENDURANCE)
