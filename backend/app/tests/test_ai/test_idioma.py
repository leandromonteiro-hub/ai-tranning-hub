"""Tudo que o atleta lê tem de sair em português.

Regressão observada em produção (2026-07-29): o prompt era inteiramente em inglês
e não trazia nenhuma instrução de idioma, então o Racional — o texto que explica
ao atleta por que aquele treino — chegava em inglês, abrindo com jargão técnico.
Para um piloto de ciclistas brasileiros, é a primeira coisa que o atleta lê no
produto.

Estes testes travam a instrução no prompt e as strings geradas em código. O que
eles NÃO podem provar é que o modelo obedece — isso só a verificação com uma
recomendação real mostra.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.models.enums import RiskLevel
from app.services.ai import prompts
from app.services.ai.recommender import _objective, _summary


def _safety(risk):
    return SimpleNamespace(risk_level=risk)


def test_system_prompt_demands_portuguese():
    assert "português" in prompts.SYSTEM_PROMPT.lower()


def test_rendered_template_demands_portuguese():
    out = prompts.render_daily_workout(
        twin="T", safety="S", evidence="E", knowledge="K", question="q",
    )
    assert "português" in out.lower()


def test_default_question_is_in_portuguese():
    """A pergunta padrão dava o tom em inglês quando o atleta não escrevia nada."""
    out = prompts.render_daily_workout(
        twin="T", safety="S", evidence="E", knowledge="K", question="",
    )
    assert "Recommend today's workout." not in out
    assert "treino de hoje" in out.lower()


def test_risk_prefixes_are_in_portuguese():
    high = _summary("# Titulo", _safety(RiskLevel.HIGH))
    moderate = _summary("# Titulo", _safety(RiskLevel.MODERATE))

    assert "CONSERVATIVE" not in high and "high-risk" not in high
    assert "PROCEED WITH CAUTION" not in moderate
    assert high.startswith("[ALTERNATIVA CONSERVADORA")
    assert moderate.startswith("[PROSSIGA COM CAUTELA]")


def test_summary_fallback_is_in_portuguese():
    """O texto vazio da IA cai neste fallback — e o atleta lia isso em inglês."""
    assert _summary("", _safety(RiskLevel.LOW)) == "Recomendação gerada."


def test_objective_stays_in_portuguese():
    """Já estava correto; o teste existe para não regredir junto com o resto."""
    assert "Recuperação" in _objective(_safety(RiskLevel.HIGH))
    assert "Estímulo" in _objective(_safety(RiskLevel.LOW))
