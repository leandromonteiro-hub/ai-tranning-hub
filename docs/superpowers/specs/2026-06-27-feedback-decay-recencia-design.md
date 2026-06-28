# Spec — Feedback ponderado por recência (decay exponencial)

**Data:** 2026-06-27
**Stream:** Training Intelligence Layer · refinamento do feedback loop
**Status:** aprovado (brainstorming), pronto para plano de implementação

## Problema

A agregação de feedback (`services/ai/feedback_context.py`) usa **média
aritmética simples** do `rating` na janela de 90 dias: uma avaliação de ontem
pesa igual a uma de 89 dias atrás. Em treinamento, a resposta recente do atleta
é mais informativa que a antiga. Ponderar por recência torna a média (geral e
por tipo de treino) mais fiel ao estado atual.

## Objetivo

Substituir a média simples por uma **média ponderada por recência** com
decaimento exponencial (meia-vida 30 dias), aplicada de forma consistente ao
agregado geral e aos buckets por tipo de treino, mantendo as funções de
agregação puras e a janela de 90 dias.

Fora de escopo (próximos candidatos): regen de perfil assíncrona (Celery);
ponderar/expor o peso por item individual; mudar o tamanho da janela.

## Decisões de design (do brainstorming)

1. **Formato:** decaimento exponencial por meia-vida — `w = 0.5^(idade/meia)`.
   Suave, um único parâmetro, nunca zera dentro da janela.
2. **Meia-vida:** 30 dias (30d→0.5, 60d→0.25, 90d→0.125). Equilibrado e seguro
   com feedback esparso (não colapsa buckets a um único ponto).
3. **O que é ponderado:** `avg_rating` e `made_sense_pct`. `count` permanece cru
   (inteiro — transparência honesta da quantidade real de avaliações).
4. **Transparência:** texto relabela para "nota média ponderada por recência";
   stats ganham `weighted=true` + `half_life_days=30`; o label do frontend
   (`feedback_line`) passa a "nota média ponderada".
5. **Pureza preservada:** `summarize`/`_rate` continuam puros; a data de
   referência (`as_of`) é injetada por `feedback_summary`, não lida via `now()`
   dentro da função pura.
6. **Janela:** `_DEFAULT_WINDOW_DAYS = 90` inalterada — limita a query; o decay
   desfavorece a borda naturalmente.

## Componente — `services/ai/feedback_context.py`

### Constante

```python
_HALF_LIFE_DAYS = 30
```

### Peso por recência

Função pura auxiliar:

```python
def _recency_weight(when: date, as_of: date) -> float:
    """Peso exponencial por recência: 0.5^(idade_dias / meia-vida).
    Idade negativa (skew de relógio / data futura) é tratada como 0 → peso 1.0."""
    age_days = max(0, (as_of - when).days)
    return 0.5 ** (age_days / _HALF_LIFE_DAYS)
```

### `_rate` ponderado

`_rate` passa a receber `as_of` e ponderar média e percentual. `count` continua
cru. Quando todos os itens têm a mesma idade, o resultado é idêntico à média
simples (os pesos se cancelam na razão).

```python
def _rate(group: list["FeedbackItem"], as_of: date) -> dict:
    n = len(group)
    weights = [_recency_weight(i.when, as_of) for i in group]
    wsum = sum(weights)
    avg = round(sum(w * i.rating for w, i in zip(weights, group)) / wsum, 1)
    answered = [(w, i.made_sense) for w, i in zip(weights, group) if i.made_sense is not None]
    if answered:
        num = sum(w for w, m in answered if m)
        den = sum(w for w, _ in answered)
        pct = round(100 * num / den)
    else:
        pct = None
    return {"count": n, "avg_rating": avg, "made_sense_pct": pct}
```

`group` é sempre não-vazio nos chamadores (só grupos com ≥1 item são criados),
e o peso exponencial é sempre > 0 para idade finita, então `wsum > 0` — sem
divisão por zero.

### `summarize` com `as_of`

Assinatura passa a `summarize(items, comment_limit=_DEFAULT_COMMENT_LIMIT, *, as_of: date)`.
Repassa `as_of` às chamadas de `_rate` (geral e por tipo). O dict `stats` ganha
as marcas de transparência; o head do texto relabela a média:

```python
stats = {**overall, "by_workout_type": by_workout_type,
         "weighted": True, "half_life_days": _HALF_LIFE_DAYS}
...
head = f"Feedback recente ({overall['count']} avaliações, nota média ponderada por recência {overall['avg_rating']}"
```

O restante de `summarize` (agrupamento por tipo, linha "Por tipo:", comentários,
caso vazio `("n/d", {})`) permanece inalterado.

### `feedback_summary`

Já calcula `cutoff` a partir de `datetime.now(timezone.utc)`. Captura esse
`now` uma vez e passa `as_of=now.date()` para `summarize`:

```python
now = datetime.now(timezone.utc)
cutoff = now - timedelta(days=window_days)
...
return summarize(items, comment_limit, as_of=now.date())
```

## Componente — frontend `intelligence_view.feedback_line`

O label da média passa a refletir a ponderação. Localizar:

```python
    if avg is not None:
        parts += f" — nota média {avg}"
```

Trocar por:

```python
    if avg is not None:
        parts += f" — nota média ponderada {avg}"
```

Sem outras mudanças no frontend. `feedback_line` continua lendo `avg_rating`
(agora ponderado) dos stats; não depende de `weighted`/`half_life_days`.

## Fluxo de dados

```
feedback_summary  →  now = now(utc);  items[ {rating, made_sense, when, ...} ]
                          │  as_of = now.date()
                          ▼
summarize(items, as_of)  →  _rate(group, as_of)  →  w_i = 0.5^(idade_i / 30)
                          │                          avg = Σ(w_i·rating_i)/Σw_i
                          ▼
stats {avg_rating (ponderado), made_sense_pct (ponderado), count (cru),
       by_workout_type, weighted:true, half_life_days:30}
       + texto "nota média ponderada por recência X · Por tipo: ..."
                          ▼
prompt {feedback}  +  payload.signals.feedback  +  feedback_line ("nota média ponderada X")
```

## Tratamento de erros / degradação

- Sem feedback (90d): `("n/d", {})` — inalterado.
- Item com data futura / skew de relógio: `age_days` clampado a 0 → peso 1.0.
- Todos os itens na mesma idade: média ponderada == média simples (sem regressão
  de comportamento perceptível).
- `made_sense` todos `None` no grupo: `made_sense_pct = None` — inalterado.

## Testes

- **`_recency_weight`** (novo unit): hoje → 1.0; 30d atrás → 0.5; 60d → 0.25;
  idade negativa → 1.0 (clamp).
- **`_rate` ponderado:** grupo com idades distintas → média ponderada ≠ média
  simples e puxa para o item recente; grupo de mesma idade → == simples;
  `made_sense_pct` ponderado; `count` cru.
- **`summarize`:** com `as_of` fixo, head contém "nota média ponderada por
  recência"; stats contêm `weighted=True` e `half_life_days=30`; buckets por
  tipo refletem a ponderação. Caso vazio inalterado.
- **`feedback_summary`:** passa `as_of` corretamente (avaliação recente domina a
  média sobre uma antiga de mesmo tipo). Isolamento por atleta e caso vazio
  permanecem verdes.
- **Frontend `feedback_line`:** caption mostra "nota média ponderada".
- Atualizar quaisquer testes existentes de `summarize`/`_rate` que agora exigem
  `as_of` na chamada (assinatura mudou).

## Critérios de aceite

1. Média geral e por tipo são ponderadas por `0.5^(idade/30)`; `count` cru.
2. `made_sense_pct` ponderado de forma consistente.
3. Funções de agregação puras (sem `now()` interno); `as_of` injetado.
4. Texto relabela; stats expõem `weighted`/`half_life_days`; frontend label
   atualizado.
5. Caso vazio e isolamento por atleta inalterados; backend pytest exit 0;
   frontend verde.
