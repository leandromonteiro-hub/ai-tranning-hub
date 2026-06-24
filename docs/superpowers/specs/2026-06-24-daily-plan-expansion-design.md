# Expansão do plano em treinos diários até a prova — Design

**Data:** 2026-06-24
**Status:** aprovado (aguardando revisão do spec)

## Objetivo

A partir de um plano periodizado existente (blocos + TSS planejado por semana),
gerar **um treino planejado por dia** (`workouts_planned`) de hoje até a data da
prova — cada dia com tipo, duração, TSS-alvo, descrição e um **treino estruturado
exportável** (.zwo/.fit). Regra (sem IA): instantâneo, grátis, determinístico. A
camada de IA (🧠 Recomendações) continua refinando a sessão real do dia a dia.

Motivação: o usuário pediu "gerar o treino de todos os dias até a prova"; a aba
Plano hoje só produz a periodização semanal (esqueleto), não treinos diários.

## Decisões

- **Geração por regra** a partir do plano (não IA por dia). Confirmado no brainstorming.
- **Descanso:** usar `AthleteProfile.weekly_days` (dias disponíveis/semana) se preenchido → `7 - weekly_days` dias de descanso/semana; senão **1 descanso/semana** (default).
- **Frontend incluído** nesta entrega (botão na aba 📅 Plano + lista dos dias), pois o objetivo é ver funcionando.
- **Treino estruturado** reusa o subsistema existente `app/services/workout/` (`templates.py`, `builder.py`, `model.py`, encoders `.zwo`/`.fit`) — os mesmos templates dos "treinos de teste".

## Arquitetura

```
Plano (TrainingPlan + TrainingWeek[blocos/TSS]) 
   → plan_expander.allocate_days(weeks, ftp, rest_per_week)  [núcleo PURO]
      → list[DailyPlanned{date, workout_type, duration_s, tss, description, structure}]
   → persist idempotente em workouts_planned (source_plan_id = plano)
```

### Componentes (unidades isoladas)
1. **`backend/app/services/planning/plan_expander.py`**
   - `allocate_days(weeks: list[WeekSpec], ftp: float | None, rest_per_week: int) -> list[DailyPlanned]` — núcleo **puro/testável**. `WeekSpec` = {week_start, block_type, planned_tss, is_recovery_week}. `DailyPlanned` = {planned_date, workout_type, planned_duration_s, planned_tss, description, structure}.
   - `async def expand_plan_to_daily(session, ctx, athlete_id, plan_id) -> dict` — carrega o plano + FTP (de `ftp_history`/`twin_seed`), chama `allocate_days`, persiste idempotente em `workouts_planned` com `source_plan_id`, retorna resumo {dias, descansos, tss_total}.
2. **Reuso** de `workout/templates.py` + `builder.py` para a `structure` jsonb de cada dia (estrutura por %FTP). Mapear o tipo do dia → template (endurance/sweet_spot/threshold/vo2max/recovery).
3. **Endpoint** `POST /plans/{plan_id}/expand` (router `/plans`) → chama `expand_plan_to_daily`, retorna o resumo + a lista dos dias.
4. **Frontend** (`frontend/app.py`, aba 📅 Plano): botão "Gerar treinos diários até a prova"; após gerar, lista os `workouts_planned` (data, tipo, duração, TSS) com download .zwo/.fit por dia (reusa as rotas de export já existentes para treino estruturado, ou expõe export por workout planejado).

### Regras de alocação (heurística documentada), por tipo de bloco
Para cada semana, escolher os dias de treino (= 7 − descansos) e distribuir o
`planned_tss` da semana entre eles segundo o padrão do bloco:
- **BASE:** maioria Z2 endurance + 1 dia de qualidade (sweet spot/tempo).
- **BUILD:** 2 dias de qualidade (threshold/VO2max) + endurance nos demais.
- **PEAK:** intensidade específica de prova (threshold/VO2), volume menor.
- **TAPER:** aberturas curtas (openers, alta intensidade/curta) + mais descanso, volume baixo.
- **RECOVERY week** (`is_recovery_week`): Z1/Z2 leve + descanso extra.
A duração de cada dia é derivada do TSS-alvo do dia e da intensidade do template
(TSS ≈ IF²·duração_h·100). Alvos de potência em %FTP usam o FTP do atleta.

## Schema (migração 0007)
- Adicionar `source_plan_id: uuid | None` (FK → `training_plans.id`, nullable) em `workouts_planned`. Espelha o `source_recommendation_id` existente. Habilita **idempotência**: re-expandir um plano apaga os `workouts_planned` daquele `source_plan_id` e recria (sem duplicar; treinos manuais/de recomendação, com `source_plan_id` nulo, não são tocados).

## Fluxo de dados e erros
- Prova no passado (race_date < hoje) → 400 "prova já ocorreu".
- Plano inexistente / de outro atleta → 404 (tenant-scoped por `ctx.athlete_id`).
- FTP ausente → tentar FTP estimado (`ftp_history` mais recente ou `twin_seed`); se nenhum, gerar estrutura por %FTP assumindo um FTP default e marcar a descrição com aviso ("FTP não definido — alvos relativos").
- Tudo escopado a `ctx.athlete_id` (isolamento multi-tenant).

## Testes
- **Núcleo `allocate_days` (TDD, puro):** distribuição do TSS semanal (soma dos dias ≈ TSS da semana), nº de descansos correto, tipos por bloco (BASE/BUILD/PEAK/TAPER/recovery), janela termina no dia da prova, FTP None tratado.
- **Endpoint (sqlite em memória):** gera N dias = (race − start + 1) menos descansos; idempotente (2ª expansão não duplica, conta estável); isolamento (atleta B não afetado); 400 para prova passada.
- **Frontend:** `ast.parse` + verificação ao vivo (botão gera e lista os dias).

## Out of scope (YAGNI)
- IA por dia (descartado no brainstorming).
- Re-otimização dinâmica do plano conforme execução (futuro).
- Sincronização com calendário externo.

## Self-review
- Cobertura: gera treino por dia até a prova (endpoint + serviço), estruturado e
  exportável (reuso workout/), idempotente (source_plan_id + migração 0007),
  frontend para ver funcionando, regras por bloco documentadas, tenant-scoped,
  testes do núcleo + endpoint + frontend. Decisões de descanso/FTP explícitas.
