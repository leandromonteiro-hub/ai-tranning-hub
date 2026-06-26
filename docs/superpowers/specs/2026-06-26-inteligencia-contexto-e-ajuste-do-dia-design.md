# Inteligência com contexto completo + Ajuste do dia (calendário ↔ recomendação) — Design Spec

**Data:** 2026-06-26
**Branch (proposta):** `feat/intel-context-day-adjustment`
**Status:** aprovado no brainstorming; pendente de plano de implementação.

## Problema

Hoje a "recomendação" da IA e o "treino planejado do dia" no calendário são **duas coisas
desconectadas**: a recomendação monta o treino estruturado de forma determinística
(`build_for(block, risk, ftp)`) e **não olha** o treino já planejado naquele dia. A IA pode
sugerir algo diferente do que está no calendário, sem reconciliação.

Além disso, ao auditar o que de fato chega à camada de inteligência, encontramos lacunas:

1. **Metodologia do treinador (engenharia reversa) chega só parcialmente.** O `twin_seed`
   (`report_builder._build_twin_seed`) grava `power_curve_bests`, `ftp_timeline`,
   `intensity_split`, `block_summary`, `best_marks`, `data_richness`. Mas a estratégia de
   **taper** (`tapers`), as **provas** (`races`) e a **terminologia do treinador**
   (`comment_terms`) — calculadas na Tarefa 2 e passadas a `build_profile_report` — **não são
   gravadas no `twin_seed`**; vivem só no markdown gitignored. E `twin_seed_summary` (o que é
   injetado no prompt) surfa apenas intensidade, marcas, contagem de blocos e riqueza. Ou seja:
   a IA sabe *como o atleta distribui intensidade e quão forte é*, mas **não sabe como o
   treinador periodizava/tapeava nem a linguagem/objetivos dos treinos**.
2. **Metodologia dos artigos (Tarefa 3) não chega à recomendação.** A base RAG
   (`CURATED_DOCUMENTS`) tem só conceitos genéricos (`source="internal_methodology"`), sem os
   achados dos artigos (MDPI/PMC). Pior: a base **só é populada manualmente**
   (`make seed-knowledge`); o startup (`main.py`) não a semeia. Se não rodada, `rag.search_knowledge`
   volta vazio → `knowledge_text="n/d"` → **nenhum conceito de metodologia entra na recomendação**.

O ajuste determinístico do dia funciona sem fechar essas lacunas, mas a **justificativa que o
LLM redige** — e a confiança percebida, que é o objetivo do projeto — fica fraca sem a
metodologia do treinador e a base de conhecimento. Por isso o trabalho é tratado num **spec
único** com quatro partes.

## Decisões tomadas (brainstorming)

1. **Direção da feature:** a IA pega o treino **já planejado** do dia e o **ajusta** ao estado
   de forma atual. O atleta mantém o planejado ou aceita a versão ajustada.
2. **Dias ajustáveis:** **hoje + dias futuros** (sempre com a forma atual). Passado nunca.
3. **Mecanismo:** ajuste **determinístico** do treino planejado por faixa de risco/forma; o
   **LLM redige a justificativa**; passa pelos guardrails. (Mantém o padrão do código: treino
   determinístico + LLM explica.)
4. **Persistência ao aceitar:** **override reversível** — o dia mostra o treino ajustado com
   marca "ajustado pela IA", o planejado original é preservado, e dá para reverter.
5. **Contexto da inteligência:** fechar as 3 lacunas (enriquecer `twin_seed`; auto-seed da base;
   ingerir achados dos artigos).
6. **Empacotamento:** **spec único** cobrindo as 4 partes.

## Arquitetura

### Parte 1a — Enriquecer `twin_seed` e injetar no prompt

**`app/services/analysis/report_builder.py` → `_build_twin_seed`:** receber e gravar, a partir
dos objetos que `build_profile_report` já tem em mãos (sem novo cálculo):

- `tapers`: lista compacta `{race_date, race_name, days_window, ctl_start, ctl_end, atl_start,
  atl_end, tsb_start, tsb_end, volume_drop_pct}` (resumo da janela de 2–3 semanas pré-prova).
- `races`: lista `{date, name, priority|type, result}` (o que `detect_races` fornece).
- `coach_terms`: top ~15 `[term, count]` de `comment_terms`.
- `periodization_summary`: `{n_blocks, meso_length_days_typical, recovery_week_cadence,
  weekly_load_progression_pct}` — **somente** o que o módulo `methodology`/`profile_metrics` já
  computa hoje. Qualquer métrica ainda não computada fica fora do escopo (não inventar cálculo).

Assinatura de `_build_twin_seed` ganha os parâmetros `tapers`, `races`, `comment_terms` (já
disponíveis em `build_profile_report`). Chaves existentes do `twin_seed` permanecem.

**`app/services/ai/profile_context.py` → `twin_seed_summary`:** acrescentar linhas compactas:

- **Taper:** ex. `"Taper típico: ~2 sem, ATL ↓ ~30%, TSB sobe pra +X antes de provas A"`.
- **Terminologia do treinador:** ex. `"Termos recorrentes do treinador: sweet spot, PMA, Z2 longo, ..."`.
- **Periodização:** ex. `"Periodização: mesos ~3–4 sem, 1 sem regen a cada 3, progressão ~+8%/sem"`.

Manter cada bloco como uma linha curta para não inflar o prompt; fallbacks `"n/d"` por seção
quando o dado falta. (O nome da função permanece para não quebrar `recommender.py`.)

**Repovoamento:** re-rodar `python -m app.scripts.analyze_athlete --email <leandro>` para
regravar o `twin_seed` com as novas chaves (também ocorre auto no próximo import produtivo, via
`/imports/upload`).

### Parte 1b — Auto-seed da base RAG no startup

**`app/bootstrap.py` → `ensure_knowledge()`** (nova, idempotente, espelha `ensure_prompt_templates`):

```python
async def ensure_knowledge() -> None:
    from app.services.knowledge.knowledge_service import ingest_curated_knowledge
    try:
        async with AsyncSessionLocal() as session:
            await ingest_curated_knowledge(session)
            await session.commit()
    except Exception:  # noqa: BLE001 — startup nunca quebra por seed de conhecimento
        log.warning("knowledge_seed_failed")
```

`ingest_curated_knowledge` já pula documentos por título existente → idempotente. Chamar em
`main.py` no lifespan, após `ensure_prompt_templates()`. Resultado: `knowledge_text` deixa de
ser `"n/d"` por base vazia. `make seed-knowledge` continua funcionando como gatilho manual.

### Parte 1c — Ingerir achados dos artigos como documentos curados

**`app/services/knowledge/document_loader.py` → `CURATED_DOCUMENTS`:** adicionar `KnowledgeDoc`s
com síntese PT-BR (derivada de `docs/training_methodology.md §12`), `athlete_id` global (NULL),
`source` = citação/URL:

- **Caso MDPI** (planejamento individualizado por IA para ciclistas de estrada): features/modelagem
  aproveitáveis para a Training Intelligence Layer. `category="ai_methodology_research"`,
  `source="https://www.mdpi.com/2076-3417/11/1/313"`.
- **Confiança/aceitação (PMC)**: o que faz atletas confiarem em planos gerados por IA —
  explicabilidade, transparência, controle do usuário, linguagem, validação.
  `category="ai_trust"`, `source="https://pmc.ncbi.nlm.nih.gov/articles/PMC11908068/"`.

Conteúdo enxuto e factual (sem prometer resultados). Por serem novos títulos, o próximo startup
(Parte 1b) os ingere automaticamente.

### Parte 2 — Ajuste do dia (a feature)

**`app/services/planning/workout_adjuster.py` (novo, puro/testável — sem I/O):**

- `adjust(structure: dict | None, risk_level: RiskLevel, ftp: float | None) -> AdjustResult`
  onde `AdjustResult = {adjusted_structure, change_summary, changed: bool}`.
- Primitivas puras sobre o dict de `StructuredWorkout`:
  - `to_recovery(structure)` — substitui por spin Z1–Z2 leve, duração reduzida, zero intensidade.
  - `cap_intensity(structure, max_zone)` — clampa targets acima de `max_zone` para o teto (e
    reduz nº de repetições de blocos de alta intensidade).
  - `scale_volume(structure, factor)` — reduz durações de blocos `active`/endurance por `factor`.
- Faixas (dirigidas pelo `risk_level` dos guardrails, que já considera fadiga/monotonia/ramp):
  - **HIGH** → `to_recovery()`.
  - **MODERATE** → `cap_intensity(Z4)` + `scale_volume(0.85)`.
  - **LOW** → sem mudança (`changed=False`); mensagem "alinhado, mantenha o planejado".
- `change_summary`: dict legível com antes/depois (TSS, duração, top-zona, nº de blocos) para o
  LLM e para a UI.

**`app/services/ai/recommender.py` → `generate_day_adjustment(...)`** (irmã de
`generate_recommendation`): carrega o `WorkoutPlanned` do dia (precisa existir; sem treino
planejado → erro tratado), reusa `build_twin` + `evaluate_safety` + evidência + RAG, chama
`workout_adjuster.adjust` (em vez de `build_for`), e renderiza o LLM **com o contexto enriquecido
da Parte 1** para escrever a justificativa. Persiste `AiRecommendation(kind="day_adjustment",
target_date, decision=PENDING)` com `payload`: `{planned_snapshot, adjusted_structure,
change_summary, signals, llm_text}`. Reaproveitar helpers existentes (`_signals`, `_confidence`,
`_summary`); extrair o que for comum sem reescrever o fluxo.

**Modelo — `app/models/workout.py` → `WorkoutPlanned.adjustment`** (coluna jsonb aditiva,
nullable) + **migração Alembic aditiva** (usar `postgresql.UUID(as_uuid=True)` se houver FK, por
convenção do projeto). Formato:

```json
{
  "structure": {...}, "tss": 0, "duration_s": 0, "workout_type": "RECOVERY",
  "reason": "texto LLM", "recommendation_id": "uuid", "adjusted_at": "iso8601"
}
```

Campos originais (`structure`, `planned_tss`, `planned_duration_s`, `workout_type`) **intactos**.

**Rotas — `app/api/routes/plans.py`** (todas tenant-scoped via `get_tenant`):

- `POST /plans/workouts/{workout_planned_id}/adjust` → valida que o dia é **hoje ou futuro** (senão
  409); chama `generate_day_adjustment`; retorna a recomendação (com `adjusted_structure`,
  `change_summary`, `reason`, risco). **Não** grava override (preview).
- `POST /plans/workouts/{workout_planned_id}/apply-adjustment` (body: `{recommendation_id}`) →
  grava o `adjustment` no `WorkoutPlanned` a partir do payload da recomendação; loga
  `AiDecision(decision=ACCEPTED)`.
- `DELETE /plans/workouts/{workout_planned_id}/adjustment` → limpa `adjustment` (reverte);
  opcionalmente loga decisão. Idempotente.

**Schema — `app/schemas/planning.py` → `PlannedWorkoutRead`:** expor `adjustment: dict | None`
(original sempre presente nos campos existentes).

**Frontend:**

- `frontend/app.py` `_render_day_detail`: para dia **hoje/futuro com treino**, botão "Ajustar com
  a IA"; ao gerar, mostra **planejado × ajustado** (dois perfis), o **motivo** (LLM), o **risco**;
  botões **Aceitar** / **Manter planejado** / (se já ajustado) **Reverter**. Após aceitar/reverter,
  `st.rerun()`.
- `frontend/app.py` `_render_calendar`: ao montar `by_date`, usar estrutura/TSS/duração/tipo
  **efetivos** (ajustado quando há override) + flag `adjusted` para o selo.
- `frontend/calendar_view.py` `_day_cell_html`: selo "🤖 IA" quando o dia tem `adjustment`. Helper
  puro `effective_workout(w: dict) -> dict` (retorna o efetivo + flag) para manter a renderização
  testável.

## Fluxo (Parte 2)

```
[Calendário] selecionar dia (hoje/futuro com treino planejado)
  └─ botão "Ajustar com a IA"
       └─ POST /plans/workouts/{id}/adjust
            ├─ valida dia ≥ hoje (senão 409)
            ├─ build_twin(as_of=dia) + guardrails → risk_level
            ├─ workout_adjuster.adjust(planejado.structure, risk_level, ftp)
            ├─ LLM redige justificativa (antes→depois + forma + contexto Parte 1)
            └─ persiste AiRecommendation(kind="day_adjustment", PENDING)
  └─ painel: planejado × ajustado + motivo + risco
       ├─ "Aceitar"  → POST .../apply-adjustment → grava override + AiDecision(ACCEPTED) → rerun
       ├─ "Manter"   → AiDecision(REJECTED)
       └─ "Reverter" → DELETE .../adjustment → rerun
```

## Testes

- **1a:** `_build_twin_seed` inclui `tapers`/`races`/`coach_terms`/`periodization_summary` (unit, a
  partir de objetos de amostra); `twin_seed_summary` renderiza as novas linhas + fallbacks `"n/d"`.
- **1b:** `ensure_knowledge` idempotente (rodar 2× não duplica docs/embeddings); base não-vazia
  após o startup simulado.
- **1c:** os novos `KnowledgeDoc`s estão em `CURATED_DOCUMENTS` (título/categoria/source) e são
  ingeridos/recuperáveis.
- **2:** `workout_adjuster` por faixa (HIGH/MODERATE/LOW) + idempotência + estruturas variadas
  (puro, sem DB); rotas `adjust`/`apply-adjustment`/`adjustment` (DELETE) com isolamento
  multi-tenant (A≠B), idempotência do apply/revert, e **dia passado rejeitado** (409); frontend:
  `effective_workout` e selo "IA" em `_day_cell_html`.

## Não-objetivos (YAGNI)

- Replanejar a semana/plano inteiro (só ajuste por dia).
- LLM gerando o treino estruturado (mantemos determinístico).
- Ajustar dias de descanso ("promover" descanso a treino) ou dias passados.
- Mover a regeneração de perfil para job assíncrono (Celery) — fica para a fase de escala.
- Job assíncrono para o `adjust` (LLM ~30–35s é aceitável inline, igual à recomendação atual).

## Princípios preservados

Separação dado real / inferido / conhecimento geral (twin_seed = inferido do real; base curada =
geral; docs de artigo = geral com citação). Todo ajuste passa pelos guardrails. Proveniência
total (override reversível, `AiDecision`, citação nas fontes). Linguagem do atleta em PT-BR,
código em inglês. Sem promessa de resultados.
