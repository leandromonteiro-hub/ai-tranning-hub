"""Versioned prompt templates with content hashing for auditability."""
from __future__ import annotations

import hashlib

SYSTEM_PROMPT = (
    "You are an evidence-based endurance cycling coach assistant. You only reason "
    "from the athlete's own historical data and the provided training-knowledge "
    "context. You never exceed a 10% weekly load increase, never ignore fatigue, "
    "sleep or HRV signals, and you clearly separate measured facts from inferred "
    "suggestions. You are an analytical support tool and never replace medical or "
    "professional evaluation. Every recommendation must be explainable and tied to "
    "the evidence provided. "
    # A instrução de idioma vem em português de propósito: escrevê-la na língua
    # de saída ancora o modelo melhor do que descrevê-la em inglês.
    "Você escreve SEMPRE em português do Brasil. Todo texto que o atleta lê — "
    "títulos, objetivo, racional, ressalvas, riscos e alternativas — sai em "
    "português. Siglas e unidades técnicas consagradas (FTP, CTL, ATL, TSB, IF, "
    "TSS, HRV, Z1-Z5, VO2max, W, km, bpm) permanecem como são."
)

DAILY_WORKOUT_TEMPLATE = """\
Athlete profile (anamnese — who this athlete is):
{profile}

Athlete training methodology (reverse-engineered from the athlete's real
training history — match their established intensity distribution, periodization
patterns and power profile unless safety requires otherwise):
{methodology}

Athlete digital-twin snapshot:
{twin}

Safety guardrail result (already computed — respect it):
{safety}

Relevant historical evidence (the athlete's own data):
{evidence}

Relevant training-knowledge context:
{knowledge}

Athlete feedback on recent recommendations (respect what worked; adjust what
was rated poorly — never promise results, never override the safety guardrail):
{feedback}

Traditional-method workout (what this athlete's own historical methodology would
prescribe today — reverse-engineered from their real training):
{methodology_workout}

When you write the recommendation, explicitly CONTRAST your recommended session
with this traditional-method one: name what the traditional method would do, then
what you recommend and WHY it differs (or say plainly if they coincide today).

Athlete question / request:
{question}

Produce a single recommendation as structured guidance including: the
physiological objective, how it relates to the current block and target race,
the supporting evidence, a confidence level (0-1) with justification, identified
risks, how to scale down if the athlete is more tired, and how to scale down if
they have less time available today. Tailor it to the athlete profile and to the
athlete's established training methodology above (intensity distribution,
periodization, power profile, experience, goals, availability, injuries).

IDIOMA DA RESPOSTA (obrigatório): escreva a recomendação inteira em português do
Brasil — inclusive o título e os cabeçalhos de seção. O atleta é brasileiro e
este texto é a explicação que ele lê para entender o treino do dia. Mantenha
siglas e unidades técnicas consagradas (FTP, CTL, ATL, TSB, IF, TSS, HRV, Z1-Z5,
VO2max, W, km, bpm) como são, sem traduzir nem explicar. Não escreva nenhuma
linha em inglês.

ESTRUTURA DA RESPOSTA (obrigatória, nesta ordem):

1. O treino de hoje, concreto: tipo de sessão, duração, zonas ou faixas de
   potência e a estrutura (aquecimento, blocos principais, volta à calma). O
   atleta precisa saber O QUE FAZER antes de qualquer outra coisa.
2. Por que esse treino: objetivo fisiológico e relação com o bloco atual e a
   prova-alvo.
3. Como ajustar: se estiver mais cansado hoje; se tiver menos tempo disponível.
4. Riscos e ressalvas — ao final, em no máximo três linhas.

SOBRE DADOS AUSENTES: quando faltar informação, NÃO abra a resposta com isso e
não liste campo por campo o que estava indisponível. Diga em uma frase, ao final,
o que a ausência limita e o que o atleta pode fazer para melhorar a próxima
recomendação (por exemplo, importar histórico ou conectar o relógio). A única
exceção: se a falta de dado impedir uma recomendação segura, diga isso primeiro,
explique por quê, e não prescreva a sessão.
"""


def render_daily_workout(
    twin: str, safety: str, evidence: str, knowledge: str, question: str,
    profile: str = "n/d", methodology: str = "n/d", feedback: str = "n/d",
    methodology_workout: str = "n/d",
) -> str:
    return DAILY_WORKOUT_TEMPLATE.format(
        profile=profile, methodology=methodology, twin=twin, safety=safety,
        evidence=evidence, knowledge=knowledge, feedback=feedback,
        methodology_workout=methodology_workout,
        question=question or "Recomende o treino de hoje.",
    )


def template_hash(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


# Registry of active templates (name -> (version, body)).
ACTIVE_TEMPLATES = {
    # v6: instrução explícita de idioma (PT-BR).
    # v7: ordem obrigatória da resposta — o treino antes das ressalvas, e a
    #     proibição de abrir enumerando dados ausentes.
    # O corpo mudou, então o hash muda e o prompt_store cria uma versão ativa
    # nova, preservando as anteriores no histórico — recomendações antigas
    # continuam rastreáveis ao prompt que as gerou.
    "daily_workout": (7, DAILY_WORKOUT_TEMPLATE),
}
