# Feedback loop — recomendações afinadas pelo feedback do atleta — Design Spec

**Data:** 2026-06-26
**Branch (proposta):** `feat/feedback-loop`
**Status:** aprovado no brainstorming; pendente de plano de implementação.

## Problema

O feedback pós-execução já é coletado (`AiRecommendationFeedback`: `rating` 1-5, `made_sense`,
`observed_result`, `comment`, ligado a uma `AiRecommendation` via `recommendation_id`) e exposto
no painel admin — mas **nunca volta à geração de recomendações**. O ciclo de aprendizado está
aberto: o atleta avalia, e a próxima recomendação ignora o que ele disse. Isso contraria o
objetivo de confiança/continuidade do projeto (o atleta precisa sentir que o sistema aprende com
ele).

## Decisões (brainstorming)

1. **Mecanismo:** **contexto no prompt** — resumir o feedback e injetá-lo como uma seção do
   prompt do LLM, espelhando o `twin_seed_summary` (`{methodology}`). A IA passa a considerar o
   que funcionou / não funcionou. (Descartado: viés determinístico mecânico — muito rígido,
   exige regras por tipo; e re-treino de modelo — fora de escopo.)
2. **Sinais:** **agregados quantitativos + comentários recentes na íntegra.** Agregados = nota
   média + taxa de "fez sentido", visão geral **e por bloco** (de `payload.signals.block`). Mais
   os últimos N comentários verbatim, cada um com data + bloco/kind.
3. **Escopo:** aplicado a **ambos** os fluxos — recomendação diária (`generate_recommendation`) e
   ajuste do dia (`generate_day_adjustment`), que compartilham `render_daily_workout`. **Degrada
   para "n/d"** quando há pouco/nenhum feedback (fase de validação, dado esparso).
4. **Transparência:** **sim** — surfacar no painel "🔍 Baseado em" (aba Recomendações) e no
   preview do ajuste que o feedback recente foi considerado. Alinhado ao achado do artigo PMC
   (explicabilidade → confiança).
5. **Agregação por bloco, não por tipo de treino:** `AiRecommendation` não tem coluna de tipo de
   treino; o **bloco** está disponível em `payload.signals.block`. Agregação por tipo de treino
   específico fica como evolução futura.

**Defaults assumidos:** janela de **90 dias**, **N=5** comentários recentes. (Ajustáveis; não
são constantes mágicas escondidas — documentadas no módulo.)

## Arquitetura

### Componente novo — `backend/app/services/ai/feedback_context.py`

Espelha `profile_context`. Função principal:

```python
async def feedback_summary(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    *,
    window_days: int = 90,
    comment_limit: int = 5,
) -> tuple[str, dict]:
    """Resumo PT-BR do feedback recente + stats para transparência.

    Retorna (texto, stats). texto = "n/d" e stats = {} quando não há feedback.
    Tenant-scoped: só lê feedback do próprio atleta.
    """
```

Lógica:
- Query `AiRecommendationFeedback` do atleta (tenant-scoped via repo/ctx), `created_at >= as_of -
  window_days`, join `AiRecommendation` para obter `payload.signals.block` e `kind`/`target_date`.
- Agrega: `count`, `avg_rating` (1 casa), `made_sense_pct` (0-100) — geral; e o mesmo **por bloco**.
- Coleta os últimos `comment_limit` comentários não-vazios (mais recentes primeiro), cada um
  formatado `"[<data> · <bloco>] <comentário>"`.
- Monta `texto` compacto PT-BR, ex.:
  `"Feedback recente (8 avaliações, nota média 4.1, fez sentido 88%). Por bloco: BUILD 3.6/5 (60% fez sentido), BASE 4.5/5. Comentários: [2026-06-20 · BUILD] muito puxado no fim; [2026-06-12 · BASE] perfeito."`
- `stats` = `{"count": int, "avg_rating": float, "made_sense_pct": int, "by_block": {...}}`.
- Sem feedback → `("n/d", {})`.

O parsing de agregados/comentários é separável em **helpers puros** (recebem listas de
feedback+recomendação já carregadas e retornam o dict/texto), testáveis sem DB; a função
`feedback_summary` faz só o I/O e delega.

### Prompt — `backend/app/services/ai/prompts.py`

- Adicionar uma seção `{feedback}` ao `DAILY_WORKOUT_TEMPLATE`, ex. (logo após `{methodology}` ou
  antes de `{question}`):
  ```
  Athlete feedback on recent recommendations (respect what worked; adjust what
  was rated poorly — never promise results, never override safety):
  {feedback}
  ```
- `render_daily_workout` ganha `feedback: str = "n/d"` e o passa ao `.format(...)`.
- `ACTIVE_TEMPLATES["daily_workout"]` sobe de `(3, ...)` para `(4, ...)`. `ensure_templates`
  (idempotente por hash) cria a v4 e desativa a v3 no próximo startup; recomendações antigas
  mantêm o `prompt_template_id` da v3 (histórico preservado).

### Recommender — `backend/app/services/ai/recommender.py`

Em `generate_recommendation` **e** `generate_day_adjustment`:
- `feedback_text, feedback_stats = await feedback_context.feedback_summary(session, ctx, athlete_id)`
- Passar `feedback=feedback_text` ao `render_daily_workout(...)`.
- Acrescentar `feedback_stats` aos signals: em `_signals(...)` (ou no ponto de montagem do
  payload) incluir `payload["signals"]["feedback"] = feedback_stats`.
  - Nota: `_signals` hoje recebe `(snapshot, methodology, block, ftp)`. Estender sua assinatura
    para receber `feedback_stats` (ou mesclar o dict após a chamada) — escolher o menor diff que
    mantenha `_signals` coeso; ambos os fluxos devem popular a mesma chave.

### Frontend — transparência

- `frontend/app.py` `recommendations_tab`, painel "🔍 Baseado em": quando
  `signals.get("feedback", {}).get("count")` > 0, renderizar uma linha:
  `"📝 Considerou suas últimas N avaliações — nota média X.X · fez sentido Y%"`.
- Preview do ajuste do dia (`_render_day_detail`): a mesma linha, lida de `preview.payload.signals.feedback`.
- A formatação dessa linha vai num **helper puro** (ex. `intelligence_view.feedback_line(stats) -> str`,
  retornando "" quando vazio) para ficar unit-testável sem streamlit.

## Fluxo de dados

```
atleta avalia recomendação → AiRecommendationFeedback (já existe)
   └─ próxima recomendação/ajuste:
        feedback_summary(athlete) → (texto, stats)
          ├─ texto → seção {feedback} do prompt → LLM adapta
          └─ stats → payload.signals.feedback → painel "🔍 Baseado em" (transparência)
```

## Tratamento de erros / casos de borda
- Sem feedback, ou só comentários vazios → `("n/d", {})`; a UI omite a linha; o prompt recebe "n/d"
  (igual às outras seções).
- Feedback de recomendações sem `signals.block` (ex.: antigas) → agrupa em bloco `"—"`/omite o
  recorte por bloco, sem quebrar.
- Isolamento multi-tenant: a query é escopada por `athlete_id`/ctx — feedback de um atleta nunca
  entra no resumo de outro (testado A≠B).

## Testes
- **`feedback_context`** (helpers puros + função com `session`/`two_athletes`): agregados corretos
  (geral + por bloco), comentários recentes na ordem certa e com rótulo data·bloco, fallback
  "n/d" sem dado, e isolamento A≠B (feedback de A ausente no resumo de B).
- **`recommender`**: `feedback` é injetado no prompt e `payload.signals["feedback"]` é populado —
  em `generate_recommendation` e em `generate_day_adjustment`.
- **`prompts`**: o template v4 contém a seção `{feedback}` e `render_daily_workout` aceita/insere
  `feedback=`; `ACTIVE_TEMPLATES["daily_workout"][0] == 4`.
- **frontend**: `feedback_line(stats)` formata corretamente e retorna "" quando `count==0`/vazio.

## Não-objetivos (YAGNI)
- Viés determinístico mecânico nos guardrails / no builder.
- Agregação por tipo de treino específico (sem coluna; bloco é o proxy).
- Fine-tuning / re-treino de modelo.
- Ponderar feedback por recência com decaimento (média simples na janela basta agora).

## Princípios preservados
Padrão de "seção de contexto no prompt" + versionamento de template (auditabilidade do
`prompt_template_id`) + transparência no painel "Baseado em". Separação dado real/inferido.
Linguagem do atleta em PT-BR, código em inglês. Sem promessa de resultados; o feedback nunca
sobrepõe os guardrails de segurança.
