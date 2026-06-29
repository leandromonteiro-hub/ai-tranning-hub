# Design — SPA do Athlete Hub: Calendário + Detalhe do Treino (nível TrainingPeaks)

Data: 2026-06-29
Status: aprovado (brainstorming) — pronto para virar plano de implementação

## 1. Contexto e objetivo

O frontend atual é Streamlit (`frontend/app.py` + `calendar_view.py` renderizando HTML/SVG
embutido). Ele é funcional para validação, mas tem teto baixo de interatividade e **não
reflete um produto concorrente do TrainingPeaks**. O usuário forneceu 5 prints de referência
do TrainingPeaks (calendário com coluna de Summary; cards de treino ricos; e a tela de
detalhe do treino com gráfico de perfil de intensidade, tabela Planned×Completed e breakdown
de steps).

Decisão estrutural (aprovada): construir uma **SPA dedicada (React/Vite/TypeScript)** que
consome a API FastAPI já existente, em vez de forçar o Streamlit. Este é o **1º ciclo** de
uma migração faseada.

**Escopo deste ciclo (aprovado):** Fundação da SPA + **Calendário** + **Detalhe do treino**.
As demais telas (Anamnese, Importar, Check-in, Provas, Recomendações, Forma & Carga) migram
em ciclos seguintes, cada um com seu próprio spec→plano.

## 2. Não-objetivos (YAGNI deste ciclo)

- Não portar as outras 6 abas do Streamlit agora.
- Não desativar o Streamlit — a SPA **roda ao lado** (porta/serviço novo) para não quebrar a
  validação em andamento.
- Não construir a "linha Metrics/Sleep" diária dos prints: **não existe fonte desse dado**
  (sem ingestão de sono/HRV). Fica deferida; não inventar dado.
- Sem drag-and-drop de treinos no calendário neste ciclo (clique→detalhe é suficiente).
- Sem edição/escrita de treino planejado pela SPA neste ciclo (só leitura + ajuste-IA que já
  existe). Criação/edição manual virá depois.

## 3. Stack (aprovada)

- **Vite + React 18 + TypeScript**.
- **Tailwind CSS + shadcn/ui** (primitivos Radix) — controle fino para UI densa.
- **TanStack Query** (cache/estado de servidor) + **React Router**.
- **Gráficos:** SVG próprio para o perfil *planejado* (blocos em degrau); **uPlot** para os
  streams por-segundo do *executado*, com coloração por zona.
- **Testes:** Vitest + React Testing Library (unit/componentes); Playwright (E2E na stack viva).
- **Auth:** `POST /auth/login` → token JWT; Bearer em todas as chamadas; `GET /auth/me` no shell;
  refresh via `POST /auth/refresh`.

## 4. Arquitetura e deployment

- Novo diretório **`web/`** na raiz do repo.
- **Dev:** Vite dev server (`:5173`) com proxy `/api` → FastAPI `:8000`.
- **Prod:** build estático (`vite build`) servido por nginx; novo serviço **`web`** no
  `docker-compose` em porta nova. `api`, `frontend` (Streamlit), `worker`, `postgres`, `redis`
  permanecem.
- Cliente de API tipado (fino wrapper sobre `fetch`) lendo `VITE_API_BASE`.

### Estrutura de pastas proposta (`web/`)
```
web/
  src/
    api/            # client fetch + hooks TanStack Query por recurso
    auth/           # contexto de auth, guarda de rota, storage do token
    components/     # primitivos shadcn + componentes compartilhados
    features/
      calendar/     # grid, célula de dia, card de treino, coluna summary, marcadores de prova
      workout/      # drawer de detalhe, gráfico de intensidade, tabela planned×completed, steps
    lib/            # lógica pura: zonas, cor de compliance, structure→perfil, formatadores
    routes/         # composição de páginas (Calendar, WorkoutDetail via rota/drawer)
  index.html, vite.config.ts, tailwind.config.ts, tsconfig.json, package.json
  Dockerfile, nginx.conf
```

## 5. Backend — 2 endpoints read-only novos (com testes)

Ambos tenant-scoped, seguindo os repositórios/padrões existentes.

### 5.1 `GET /calendar?start=<date>&end=<date>`
Agrega numa só resposta o que a tela de calendário precisa, evitando N chamadas no cliente.

Forma (esboço):
```jsonc
{
  "days": [
    {
      "date": "2026-05-12",
      "planned": [ { "id","name","workout_type","planned_duration_s","planned_tss",
                     "description","structure","adjustment" } ],   // de WorkoutPlanned
      "completed": [ { "id","name","workout_type","duration_s","distance_m",
                       "tss","intensity_factor","avg_power","normalized_power",
                       "avg_hr","kj","notes" } ],                   // de WorkoutCompleted
      "races": [ { "id","name","race_date","days_until" } ]        // marcadores
    }
  ],
  "weeks": [
    { "week_start":"2026-05-11", "ctl":..,"atl":..,"tsb":..,        // de /metrics/load (PMC)
      "total_duration_s":..,"total_tss":..,"total_distance_m":..,
      "total_elevation_m":..,"total_kj":.. }
  ]
}
```
- `planned` reutiliza a leitura por intervalo de datas (novo método de repositório
  `list_planned_between` — hoje só existe listagem por `plan_id`).
- `completed` reutiliza `WorkoutRepository.list_between` (já existe).
- `weeks` reutiliza os pontos PMC de `/metrics/load`; totais agregados por semana ISO.

### 5.2 `GET /workouts/{id}/streams?max_points=<n>`
Streams *downsampled* para o gráfico do detalhe; carregado sob demanda ao abrir o treino.
```jsonc
{ "workout_id":"...", "sample_rate_hz":1.0, "n_points":1200,
  "time_s":[...], "power":[...], "heart_rate":[...], "cadence":[...], "altitude":[...] }
```
- Downsample por *bucketing* (média por bucket) até `max_points` (default ~1000–1500) para não
  trafegar arrays de horas inteiras por segundo.
- 404 se o treino não existe / não pertence ao tenant. Streams ausentes → arrays vazios.

## 6. Tela A — Calendário (espelha os prints)

App shell: top-nav (logo, Calendar/Dashboard, usuário/sair) + barra de controle (mês/semana,
botão Today, setas ‹ ›). Grid **7 colunas (Seg–Dom) + coluna Summary** à direita.

**Célula de dia:** cabeçalho com número/data (hoje destacado), 0..N cards, marcadores de prova,
"Day Off/Descanso" quando aplicável.

**Card de treino:**
- Faixa de cor superior por *compliance*: executado-no-alvo, executado-fora, planejado-pendente,
  ajustado-pela-IA. Mapa de cores definido em `lib/compliance.ts`.
- Ícone do esporte, título, duração (`h:mm:ss`, com ✓ se executado), distância, **TSS**.
- Preview dos steps estruturados (primeiras linhas do `structure`/descrição).
- **Mini-thumbnail de intensidade (SVG)** derivado do `structure` (planejado) ou de um resumo
  do stream (executado).
- Rodapé: RPE/emoji, ícone de comentário, ícone de força (quando houver no `extra`).
- **Badge "🤖 IA"** quando `adjustment` presente (mostra valores efetivos).

**Marcadores de prova:** contagem regressiva ("5 DAYS UNTIL EVENT" + nome), a partir de `races`.

**Coluna Summary** (por linha-semana): Fitness/Fatigue/Form (CTL/ATL/TSB), Total Duração,
Total TSS, Total Distância, El. Gain, Work (kJ). Barras proporcionais como nos prints.

Clique num card → abre **Tela B**.

## 7. Tela B — Detalhe do treino (espelha modelo_treino_planilhado)

Abre como **drawer/modal** sobre o calendário (rota aninhada `/calendar/workout/:id`).

- **Cabeçalho:** data, título, esporte, duração, distância, TSS, IF.
- **Gráfico de perfil de intensidade:**
  - *Planejado:* blocos em degrau a partir de `structure` (SVG), coloridos por zona.
  - *Executado:* stream de potência por-segundo via **uPlot**, com bandas/coloração por zona;
    sobreposição opcional de HR.
- **Tabela Planned × Completed:** Duração, Distância, TSS, IF, NP, Work/kJ, Elevation Gain/Loss.
- **Min/Avg/Max:** potência, HR, cadência — avg/max do banco; min derivado dos streams quando
  disponíveis.
- **Breakdown de steps:** lista "Warm up / Active / Recovery / Cool Down" → "N min @ X–Y W,
  Zona Z" a partir de `structure`.
- **Descrição/notas** (read-only neste ciclo).
- **Painel de ajuste-IA:** quando ajustado, mostra original × ajustado + ação de reverter,
  reaproveitando `POST /plans/workouts/{id}/adjust`, `.../apply-adjustment` e `DELETE
  .../adjustment` (já existentes).

## 8. Lógica pura (testável isoladamente — `web/src/lib/`)

- `zones.ts` — mapeia potência→zona (Z1..Z7) dado o FTP; faixas e cores por zona.
- `compliance.ts` — deriva a cor da faixa do card (executado/planejado/ajustado/fora-do-alvo).
- `structure.ts` — `structure` (jsonb de blocos) → array de segmentos `{durationS, lowW, highW,
  zone}` para o perfil planejado e para o preview de steps.
- `summary.ts` — agrega totais por semana ISO a partir dos dias (espelha o backend; usado se/onde
  o cliente precisar recompor).
- `format.ts` — duração, distância, TSS, datas.

Cada uma é função pura, sem React/fetch → coberta por Vitest.

## 9. Fluxo de dados

1. App carrega → auth (token em memória + refresh) → `GET /auth/me` popula o shell.
2. Calendário monta intervalo visível → `useCalendar(start,end)` (TanStack Query) → `GET /calendar`.
3. Clique no card → rota `/calendar/workout/:id` → `useWorkout(id)` (detalhe básico já no payload
   do calendário ou `GET /workouts/{id}`) + `useWorkoutStreams(id)` sob demanda → `GET
   /workouts/{id}/streams`.
4. Ajuste-IA dispara mutações nos endpoints existentes; invalida o cache do calendário.

## 10. Estratégia de testes

- **Backend (pytest):** `/calendar` (filtro por intervalo, agregação semanal, isolamento
  multi-tenant, vazio); `/workouts/{id}/streams` (downsample até `max_points`, 404, streams
  ausentes, isolamento).
- **Frontend unit (Vitest):** todas as funções de `lib/` (zonas, compliance, structure→perfil,
  summary, format).
- **Frontend componentes (RTL):** card de treino (variações de compliance/IA), coluna summary,
  drawer de detalhe (planejado vs executado).
- **E2E (Playwright, opcional no ciclo):** login → calendário renderiza semana real do Leandro →
  abre um treino → gráfico + tabela aparecem. Roda contra a stack viva (`docker compose up`).

## 11. Riscos e mitigações

- **Volume de streams:** treinos longos têm milhares de pontos/segundo → downsample no backend
  (5.2) e uPlot no front.
- **Conviver com Streamlit:** porta/serviço separado; nenhum endpoint existente muda de contrato
  (só adições) → Streamlit não quebra.
- **Dados ausentes/parciais:** cards e tabela degradam graciosamente (sem distância, sem NP,
  sem streams) — nunca quebrar a renderização.
- **Paridade visual com os prints:** os prints são a referência de aceite; divergências
  conscientes (ex.: linha Metrics deferida) ficam documentadas aqui.

## 12. Critérios de aceite do ciclo

- SPA sobe em dev (proxy→API) e em docker (serviço `web`), sem afetar o Streamlit.
- Login funciona contra a API atual.
- Calendário renderiza a semana real do atleta de validação com cards ricos + coluna Summary +
  marcadores de prova, visualmente alinhado aos prints (exceto a linha Metrics, deferida).
- Clique num treino abre o detalhe com gráfico de intensidade (planejado e/ou executado),
  tabela Planned×Completed, Min/Avg/Max e breakdown de steps.
- Backend: 2 endpoints novos com testes verdes; nenhum contrato existente alterado.
- Lógica pura do front coberta por Vitest; componentes-chave por RTL.
