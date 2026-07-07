# Dashboard "Visão geral" com dados reais + landing unificada

**Data:** 2026-07-07 · **Status:** aprovado
**Contexto:** a landing `web/app/(app)/page.tsx` é um placeholder (4 cards com
"—" e nota "M2"). No piloto em produção isso faz o app parecer vazio — o
usuário admin-atleta cai no Painel do treinador e não encontra seu treino,
apesar de todos os dados existirem. Esta spec substitui o placeholder por um
dashboard real e unifica a landing.

## Decisões (aprovadas pelo usuário)

- **3 cards**: Forma (TSB), Próximo treino planejado, Semana + recomendação.
  (Próxima prova ficou de fora agora — dados existem, fácil de somar depois.)
- **Landing unificada**: admin-que-também-é-atleta cai na Visão geral (`/`),
  não no `/admin`. O "Painel do treinador" segue no menu.
- **Zero backend novo**: tudo via hooks SWR existentes + cálculo client-side.

## Arquitetura

- `web/app/(app)/page.tsx` (server, fino) → renderiza `<OverviewView />`
  (client), mesmo padrão de `anamnese/page.tsx` → `AnamneseView`.
- `web/components/overview/OverviewView.tsx` — client component que orquestra
  os hooks e os 3 cards. Cards podem ser subcomponentes no mesmo arquivo ou
  arquivos próprios se crescerem; cada um lê seu hook e trata loading/vazio.
- Reuso: `Card`/`Badge`/`Button` (ui), `FormCards` e helpers `formState.ts`
  (`formReading`, `formTone`, `TONE_TEXT`, `currentFtp`), date helpers
  (`web/lib/dateUtils.ts` `todayIso`, `web/lib/weekRange.ts`).

## Cards (fonte de dados — tudo já existe)

### 1. Forma (TSB)
- Fonte: `useIntelligence()` → `intel.form { metric_date, ctl, atl, tsb }`.
- Mostra: TSB grande com cor/leitura de `formReading(tsb)`/`formTone(tsb)`;
  linha secundária CTL / ATL. Reusa `FormCards` (já é a fileira 3-up
  CTL/ATL/TSB) OU um tile compacto — implementação escolhe o mais limpo.
- Ação: card inteiro é link para `/forma-carga`.
- Vazio: `intel` null ou `form` null (sem dados de carga) → "Sem dados de
  forma ainda — importe treinos" + link `/importar`.

### 2. Próximo treino planejado
- Fonte: `useCalendar(todayIso(), today+14d)` → `resp.days[].planned[]`;
  achatar e pegar o primeiro `PlannedWorkout` com `planned_date >= hoje`.
- Mostra: nome, `workout_type`, duração (`planned_duration_s`), `planned_tss`.
- Ação: link `/plano`.
- Vazio: nenhum planejado nos 14 dias → "Nenhum treino planejado" + link
  `/recomendacoes` (gerar).

### 3. Semana + recomendação
- Fonte A: `useCalendar` (mesma chamada ou uma cobrindo a semana atual) →
  `resp.weeks` → a `WeekSummary` cujo `week_start` == início da semana atual
  (`weekRange`); mostra `total_tss`, `total_duration_s` (→ horas),
  `total_distance_m` (→ km).
- Fonte B: `useRecommendations()` → mais recente por `created_at` → `summary`.
- Mostra: totais da semana + resumo (truncado) da recomendação.
- Ação: link `/recomendacoes`.
- Vazio: sem semana → zeros; sem recomendação → "Nenhuma recomendação ainda"
  + botão/label gerar.

## Cabeçalho

Mantém o título "Visão geral" + subtítulo, e o botão "Gerar recomendação"
(link `/recomendacoes`) que já existe no placeholder.

## Landing por role

Hoje dois handlers em `web/app/(auth)/login/page.tsx` fazem
`router.push(role === "ADMIN" ? "/admin" : "/")` (fluxo email e fluxo Google).
Trocar ambos para `router.push("/")` — todos caem na Visão geral. O
`Sidebar` já mostra "Painel do treinador" só para ADMIN (inalterado), então
o admin não perde acesso. Nenhuma mudança de backend/rota; `/` já vive dentro
do shell `(app)` acessível a admin.

## Estados e erros

- Cada card: skeleton enquanto `isLoading`; mensagem de vazio própria; erro
  de hook (SWR) degrada para o estado vazio do card, nunca quebra a página.
- Página nunca depende de um único hook para renderizar — um card com erro
  não afeta os outros.

## Testes (vitest + @testing-library/react)

`web/components/overview/__tests__/OverviewView.test.tsx`:
- Forma: com `intel.form` mockado mostra o TSB e a leitura; sem form mostra o
  vazio com link `/importar`.
- Próximo treino: com calendar mockado (um planejado futuro) mostra nome/tipo;
  sem planejado mostra o vazio.
- Semana + recomendação: com weeks + recommendations mockados mostra totais e
  resumo; sem recomendação mostra o vazio.
- Header: título "Visão geral" e botão "Gerar recomendação" presentes.

`web/app/(auth)/login/__tests__/LoginPage.test.tsx` (ajuste): admin agora vai
para `/` (não `/admin`) nos dois fluxos (email e Google).

## Fora de escopo

- Card de Próxima prova (dados existem; somar depois).
- Novos endpoints/campos de backend.
- Refactor das telas Forma & Carga / Plano / Recomendações (o dashboard só
  resume e linka).
- Filtro de "recomendação de hoje" por kind/target_date (usa a mais recente,
  como as outras telas já fazem).
