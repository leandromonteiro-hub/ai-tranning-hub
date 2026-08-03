# Botão "Gerar plano" + horizonte das bandeiras de prova — design

Data: 2026-08-02 · Status: aprovado pelo Leandro (chat)

## Problema

1. O endpoint de gerar plano (`POST /plans/generate` + `POST /plans/{id}/expand`)
   existe desde o início, mas **nenhuma tela chama** — o atleta não consegue
   gerar o próprio calendário (hoje foi feito via API na mão).
2. Gerar duas vezes para a mesma prova **duplica planos** e treinos no
   calendário — não há semântica de substituição.
3. Com 3+ provas cadastradas, o calendário mostra uma bandeira de contagem
   por prova em **todos** os dias — poluição visual (a Cape Epic a 233 dias
   aparece em cada célula).

## Decisões (conversadas)

- Botão **por prova, na página Provas** (fluxo: cadastrou → gera o plano até ela).
- **Regenerar substitui**: plano anterior da mesma prova é arquivado; treinos
  futuros dele saem, passados ficam.
- Bandeira de contagem só para provas a **até 30 dias**; durante a prova
  continua sempre visível.

## 1. Backend — substituição no generate

`POST /plans/generate` (routes/plans.py): antes de criar, se `target_race_id`
foi informado e existe `TrainingPlan` ativo (`deleted_at IS NULL`) com o mesmo
`target_race_id`:

- soft-delete do plano antigo (`deleted_at = now()`);
- hard-delete dos treinos futuros dele:
  `WorkoutPlanned.source_plan_id == plano_antigo.id AND planned_date >= hoje`.
  Treinos passados ficam (histórico de compliance).

Sem `target_race_id`, comportamento atual (cria mais um plano) — sem mudança.

## 2. Web — botão na página Provas

`ProvasView`: em cada linha de prova **futura** (`(end_date ?? race_date) >=
hoje`), botão "Gerar plano". Clique:

1. `POST plans/generate` com `{name: "Plano — {nome}", race_date, target_race_id: id, priority}`;
2. `POST plans/{id}/expand`;
3. estado de sucesso na linha: "Plano gerado: N treinos" + link "Ver plano" → `/plano`;
4. erro → mensagem "Não foi possível gerar o plano." na linha; botão volta ao normal.

Enquanto roda: botão desabilitado com "Gerando…" (a geração de 33 semanas leva
alguns segundos). Provas passadas: sem botão.

## 3. Web — horizonte das bandeiras

`lib/races.ts`: `showRaceFlag(daysUntil: number): boolean` → `daysUntil <= 30`
(cobre o durante-a-prova, que é `<= 0`). `CalendarGrid` filtra `day.races` com
esse helper. Constante de 30 dias vive no helper. Backend intacto.

## Testes

- **Backend** (`test_api/test_plan_expand.py` ou arquivo novo): gerar 2x para a
  mesma prova → 1 plano ativo; treinos futuros são do plano novo; treino
  passado do plano antigo permanece; gerar sem `target_race_id` não arquiva nada.
- **Web** `ProvasView`: botão aparece só em prova futura; clique dispara
  generate+expand e mostra sucesso; erro de generate mostra mensagem.
- **Web** `races.test.ts`: `showRaceFlag` (31 → false, 30/0/-2 → true).
- **Web** `CalendarGrid`: prova a 60 dias não renderiza bandeira; a 8 dias
  renderiza (teste existente cobre); durante a prova renderiza (existente).

## Fora de escopo

- Escolher prioridade/nome do plano na UI (usa os da prova).
- Cancelar/apagar plano pela UI.
- Mudar a agregação do backend de marcadores (filtro é visual).
