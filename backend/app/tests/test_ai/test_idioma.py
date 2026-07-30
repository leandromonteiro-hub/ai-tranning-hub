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


def test_template_orders_workout_before_caveats():
    """O atleta precisa ler o treino antes de ler o que faltou nos dados.

    Regressão observada: com anamnese só (o mínimo obrigatório do piloto), a IA
    abria com um bloco de ressalvas listando campo por campo o que estava
    indisponível. O atleta novo lia "não consigo personalizar" antes de saber o
    que fazer hoje.
    """
    body = prompts.DAILY_WORKOUT_TEMPLATE.lower()

    assert "estrutura da resposta" in body
    # A ordem tem de estar explícita no texto: treino primeiro, ressalvas ao fim.
    assert body.index("o treino de hoje") < body.index("riscos e ressalvas")


def test_template_forbids_opening_with_missing_data():
    body = prompts.DAILY_WORKOUT_TEMPLATE.lower()

    assert "não abra a resposta" in body
    assert "campo por campo" in body  # proíbe a enumeração do que faltou


def test_template_keeps_the_safety_escape_hatch():
    """Se a falta de dado impedir recomendação segura, aí sim vem primeiro."""
    assert "impedir uma recomendação segura" in prompts.DAILY_WORKOUT_TEMPLATE


def test_active_template_version_bumped_for_structure():
    assert prompts.ACTIVE_TEMPLATES["daily_workout"][0] == 7
