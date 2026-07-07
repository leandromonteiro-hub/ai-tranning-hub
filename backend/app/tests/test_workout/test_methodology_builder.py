"""Builder do 'método tradicional': treino no estilo histórico do atleta."""
from __future__ import annotations

from app.models.enums import BlockType, RiskLevel
from app.services.workout import analysis
from app.services.workout.methodology_builder import (
    build_methodology_workout,
    typical_duration_for,
)
from app.services.workout.model import Repeat


def _total_s(w) -> int:
    return analysis.total_duration_s(w)


def test_typical_duration_median_when_enough_history():
    assert typical_duration_for([3600, 5400, 7200], BlockType.BASE) == 5400


def test_typical_duration_fallback_per_block_when_sparse():
    assert typical_duration_for([], BlockType.BASE) == 5400
    assert typical_duration_for([3600], BlockType.PEAK) == 3600  # <3 amostras


def test_pyramidal_base_is_endurance_scaled_to_typical():
    split = {"z1_pct": 0.68, "z2_pct": 0.29, "z3_pct": 0.03}
    w = build_methodology_workout(split, BlockType.BASE, 250.0, 5400, RiskLevel.LOW)
    # Endurance (sem repeats de intensidade) e duração ~= típica.
    assert not any(isinstance(el, Repeat) for el in w.elements)
    assert abs(_total_s(w) - 5400) <= 60
    assert "seu padrão" in w.name.lower()
    assert w.estimated_tss and w.estimated_tss > 0


def test_threshold_history_build_has_intervals():
    split = {"z1_pct": 0.55, "z2_pct": 0.25, "z3_pct": 0.20}
    w = build_methodology_workout(split, BlockType.BUILD, 250.0, 4500, RiskLevel.LOW)
    assert any(isinstance(el, Repeat) for el in w.elements)


def test_high_risk_forces_recovery():
    split = {"z1_pct": 0.55, "z2_pct": 0.25, "z3_pct": 0.20}
    w = build_methodology_workout(split, BlockType.BUILD, 250.0, 4500, RiskLevel.HIGH)
    assert "recupera" in w.name.lower()


def test_missing_split_falls_back_to_generic_block_template():
    w = build_methodology_workout(None, BlockType.BASE, 250.0, 5400, RiskLevel.LOW)
    # Cai no build_for (genérico) — nome do template padrão, não "seu padrão".
    assert "seu padrão" not in w.name.lower()
    assert w.estimated_tss and w.estimated_tss > 0
