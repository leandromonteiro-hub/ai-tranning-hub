"""Builder do treino que o MÉTODO TRADICIONAL do atleta (twin do histórico
prescreveria hoje. Determinístico e puro: distribuição de intensidade + bloco +
duração típica -> StructuredWorkout no estilo do atleta. Sem histórico/dados
ralos, cai no template genérico do bloco (build_for)."""
from __future__ import annotations

from statistics import median

from app.models.enums import BlockType, RiskLevel
from app.services.workout import analysis
from app.services.workout.builder import build_for
from app.services.workout.model import Repeat, Step, StructuredWorkout, Target

# Fallback de duração por bloco (segundos) quando o histórico é ralo.
_FALLBACK_DURATION_S: dict[BlockType, int] = {
    BlockType.BASE: 5400,
    BlockType.BUILD: 4500,
    BlockType.PEAK: 3600,
    BlockType.TAPER: 2700,
    BlockType.RECOVERY: 2700,
}
# Acima deste share de Z3 histórico consideramos que o atleta faz intensidade.
_Z3_INTERVAL_THRESHOLD = 0.15
_MIN_HISTORY = 3  # amostras mínimas para usar a mediana em vez do fallback


def typical_duration_for(durations_s: list[int], block_type: BlockType) -> int:
    usable = [d for d in durations_s if d and d > 0]
    if len(usable) >= _MIN_HISTORY:
        return int(median(usable))
    return _FALLBACK_DURATION_S.get(block_type, 5400)


def _pwr(low: float, high: float) -> Target:
    return Target(type="power_pct_ftp", low=low, high=high)


def _endurance(typical_s: int) -> list[Step | Repeat]:
    """Z2 do tamanho típico: 10min aquece, bloco Z2, 10min desaquece."""
    main = max(600, typical_s - 1200)
    return [
        Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.60)),
        Step(intensity="active", duration_s=main, target=_pwr(0.62, 0.68)),
        Step(intensity="cooldown", duration_s=600, target=_pwr(0.40, 0.50)),
    ]


def _intervals(typical_s: int, work_s: int, rest_s: int, low: float, high: float) -> list[Step | Repeat]:
    """Sessão de intervalos ajustando o nº de reps p/ caber na duração típica."""
    budget = max(0, typical_s - 1200)  # tira aquecimento + desaquecimento
    reps = max(2, min(6, budget // (work_s + rest_s)))
    return [
        Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.65)),
        Repeat(count=int(reps), steps=[
            Step(intensity="active", duration_s=work_s, target=_pwr(low, high)),
            Step(intensity="rest", duration_s=rest_s, target=_pwr(0.50, 0.55)),
        ]),
        Step(intensity="cooldown", duration_s=600, target=_pwr(0.40, 0.50)),
    ]


def build_methodology_workout(
    intensity_split: dict | None,
    block_type: BlockType,
    ftp_watts: float,
    typical_duration_s: int,
    risk_level: RiskLevel,
) -> StructuredWorkout:
    # Mesmo guardrail do build_for: HIGH risk -> recuperação.
    if risk_level == RiskLevel.HIGH:
        w = build_for(block_type, RiskLevel.HIGH, ftp_watts)
        w.name = "Recuperação Z1 (seu padrão)"
        return w

    z3 = (intensity_split or {}).get("z3_pct")
    if not intensity_split or z3 is None:
        # Sem histórico suficiente -> template genérico do bloco (honesto).
        return build_for(block_type, risk_level, ftp_watts)

    does_intensity = float(z3) >= _Z3_INTERVAL_THRESHOLD
    if does_intensity and block_type in (BlockType.BUILD, BlockType.PEAK):
        if block_type == BlockType.PEAK:
            elements = _intervals(typical_duration_s, 240, 240, 1.10, 1.18)
            name = "VO2max (seu padrão)"
        else:
            elements = _intervals(typical_duration_s, 720, 300, 0.88, 0.93)
            name = "Sweet Spot (seu padrão)"
    else:
        # Pirâmidal / pouco Z3 / blocos de base -> pão-com-manteiga Z2.
        elements = _endurance(typical_duration_s)
        name = "Endurance Z2 (seu padrão)"

    workout = StructuredWorkout(name=name, elements=elements, ftp_watts=ftp_watts)
    workout.estimated_tss = analysis.estimated_tss(workout)
    return workout
