# Dashboard "Visão geral" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir a landing placeholder (`web/app/(app)/page.tsx`, cards com "—") por um dashboard real com 3 cards (Forma/TSB, Próximo treino, Semana+recomendação) e fazer todo mundo cair nele ao entrar.

**Architecture:** Puro frontend. Uma camada de helpers puros deriva os dados dos hooks SWR existentes; o `OverviewView` (client) monta os 3 cards reusando `Card`/`Badge` e os helpers de `formState.ts`. Nenhum backend novo. A landing por role muda só nos dois `router.push` do login.

**Tech Stack:** Next.js 15 App Router, React 19, SWR, Tailwind, vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-07-07-dashboard-visao-geral-design.md`

## Global Constraints

- UI em **pt-BR**; reusar `Card`/`Badge`/`Button` de `web/components/ui/` e helpers de `web/lib/formState.ts`; **zero backend novo**.
- Testes web no host: `cd web && npx vitest run <PATH>`.
- Branch: `feat/dashboard-visao-geral` (já existe, spec commitada).
- Commits terminam com `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Tipos existentes (verbatim, de `web/lib/types.ts`): `CalendarResponse = { days: CalendarDay[]; weeks: WeekSummary[] }`; `PlannedWorkout` tem `planned_date, name, workout_type, planned_duration_s, planned_tss`; `WeekSummary` tem `week_start, total_tss, total_duration_s, total_distance_m`; `Recommendation` tem `summary, created_at`; `AthleteIntelligence.form` é `FormState { metric_date, ctl, atl, tsb } | null`.

---

### Task 1: Helpers puros de derivação (`web/lib/overview.ts`)

**Files:**
- Create: `web/lib/overview.ts`
- Test: `web/lib/__tests__/overview.test.ts`

**Interfaces:**
- Consumes: tipos `CalendarResponse`, `PlannedWorkout`, `WeekSummary`, `Recommendation` de `@/lib/types`; `mondayOf` de `@/lib/weekRange`.
- Produces:
  - `addDaysIso(iso: string, n: number): string`
  - `nextPlannedWorkout(cal: CalendarResponse | undefined, todayIso: string): PlannedWorkout | null`
  - `currentWeekSummary(cal: CalendarResponse | undefined, todayIso: string): WeekSummary | null`
  - `mostRecentRec(recs: Recommendation[] | undefined): Recommendation | null`

- [ ] **Step 1: Escrever os testes que falham**

Criar `web/lib/__tests__/overview.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { addDaysIso, nextPlannedWorkout, currentWeekSummary, mostRecentRec } from '@/lib/overview'
import type { CalendarResponse, Recommendation } from '@/lib/types'

const planned = (id: string, date: string) => ({
  id, planned_date: date, name: `T-${id}`, workout_type: 'endurance',
  planned_duration_s: 3600, planned_tss: 50, description: null, structure: null, adjustment: null,
})
const week = (start: string) => ({
  week_start: start, ctl: 50, atl: 40, tsb: 10,
  total_duration_s: 7200, total_tss: 120, total_distance_m: 60000, total_elevation_m: 500, total_kj: 1800,
})

describe('addDaysIso', () => {
  it('soma dias cruzando mês', () => {
    expect(addDaysIso('2026-07-05', 14)).toBe('2026-07-19')
    expect(addDaysIso('2026-06-25', 10)).toBe('2026-07-05')
  })
})

describe('nextPlannedWorkout', () => {
  const cal: CalendarResponse = {
    days: [
      { date: '2026-07-06', planned: [planned('a', '2026-07-06')], completed: [], races: [] },
      { date: '2026-07-08', planned: [planned('b', '2026-07-08')], completed: [], races: [] },
    ],
    weeks: [],
  }
  it('pega o primeiro planejado com data >= hoje', () => {
    expect(nextPlannedWorkout(cal, '2026-07-07')?.id).toBe('b')
  })
  it('inclui hoje', () => {
    expect(nextPlannedWorkout(cal, '2026-07-06')?.id).toBe('a')
  })
  it('null quando não há futuro', () => {
    expect(nextPlannedWorkout(cal, '2026-07-09')).toBeNull()
    expect(nextPlannedWorkout(undefined, '2026-07-07')).toBeNull()
  })
})

describe('currentWeekSummary', () => {
  const cal: CalendarResponse = { days: [], weeks: [week('2026-07-06'), week('2026-06-29')] }
  it('acha a semana cujo week_start é a segunda de hoje', () => {
    // 2026-07-08 é uma quarta; a segunda da semana é 2026-07-06
    expect(currentWeekSummary(cal, '2026-07-08')?.week_start).toBe('2026-07-06')
  })
  it('null quando não há semana correspondente', () => {
    expect(currentWeekSummary(cal, '2026-08-01')).toBeNull()
    expect(currentWeekSummary(undefined, '2026-07-08')).toBeNull()
  })
})

describe('mostRecentRec', () => {
  const mk = (id: string, created: string): Recommendation => ({
    id, target_date: null, kind: 'daily_workout', summary: `S-${id}`,
    physiological_objective: null, block_relation: null, rationale: null,
    adjust_if_tired: null, adjust_if_less_time: null, payload: null,
    risk_level: 'LOW', risk_flags: null, confidence: null, confidence_rationale: null,
    decision: 'PENDING', created_at: created, evidence: [],
  })
  it('retorna a mais recente por created_at', () => {
    expect(mostRecentRec([mk('a', '2026-07-01T00:00:00Z'), mk('b', '2026-07-05T00:00:00Z')])?.id).toBe('b')
  })
  it('null p/ lista vazia ou undefined', () => {
    expect(mostRecentRec([])).toBeNull()
    expect(mostRecentRec(undefined)).toBeNull()
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run lib/__tests__/overview.test.ts`
Expected: FAIL — `Cannot find module '@/lib/overview'`

- [ ] **Step 3: Implementar**

Criar `web/lib/overview.ts`:

```ts
import type { CalendarResponse, PlannedWorkout, Recommendation, WeekSummary } from '@/lib/types'
import { mondayOf } from '@/lib/weekRange'

/** Soma n dias a uma data ISO (YYYY-MM-DD), em UTC. */
export function addDaysIso(iso: string, n: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d))
  dt.setUTCDate(dt.getUTCDate() + n)
  return dt.toISOString().slice(0, 10)
}

/** Primeiro treino planejado com data >= hoje (ordena por data). */
export function nextPlannedWorkout(
  cal: CalendarResponse | undefined, todayIso: string,
): PlannedWorkout | null {
  if (!cal) return null
  const future = cal.days
    .flatMap((day) => day.planned)
    .filter((p) => p.planned_date >= todayIso)
    .sort((a, b) => a.planned_date.localeCompare(b.planned_date))
  return future[0] ?? null
}

/** Resumo da semana atual (week_start == segunda de hoje). */
export function currentWeekSummary(
  cal: CalendarResponse | undefined, todayIso: string,
): WeekSummary | null {
  if (!cal) return null
  const monday = mondayOf(todayIso)
  return cal.weeks.find((w) => w.week_start === monday) ?? null
}

/** Recomendação mais recente por created_at. */
export function mostRecentRec(recs: Recommendation[] | undefined): Recommendation | null {
  if (!recs || recs.length === 0) return null
  return [...recs].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run lib/__tests__/overview.test.ts`
Expected: todos verdes

- [ ] **Step 5: Commit**

```bash
git add web/lib/overview.ts web/lib/__tests__/overview.test.ts
git commit -m "feat(web): helpers puros de derivação p/ o dashboard Visão geral

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: OverviewView + 3 cards + página

**Files:**
- Create: `web/components/overview/OverviewView.tsx`
- Modify: `web/app/(app)/page.tsx` (substitui o placeholder)
- Test: `web/components/overview/__tests__/OverviewView.test.tsx`

**Interfaces:**
- Consumes: `useIntelligence`, `useCalendar`, `useRecommendations` de `@/lib/hooks`; `nextPlannedWorkout`, `currentWeekSummary`, `mostRecentRec`, `addDaysIso` de `@/lib/overview`; `todayIso` de `@/lib/dateUtils`; `mondayOf` de `@/lib/weekRange`; `formReading`, `formTone`, `TONE_TEXT` de `@/lib/formState`; `Card`/`Button` de `@/components/ui/*`.
- Produces: `OverviewView()` (named export). Página `page.tsx` renderiza `<OverviewView />`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `web/components/overview/__tests__/OverviewView.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { OverviewView } from '@/components/overview/OverviewView'
import { useIntelligence, useCalendar, useRecommendations } from '@/lib/hooks'
import { mondayOf } from '@/lib/weekRange'

vi.mock('@/lib/hooks', () => ({
  useIntelligence: vi.fn(),
  useCalendar: vi.fn(),
  useRecommendations: vi.fn(),
}))

const swr = (data: unknown, isLoading = false) => ({ data, error: undefined, isLoading, mutate: vi.fn() })

function setup(over: {
  intel?: unknown; cal?: unknown; recs?: unknown
} = {}) {
  ;(useIntelligence as Mock).mockReturnValue(swr(over.intel))
  ;(useCalendar as Mock).mockReturnValue(swr(over.cal))
  ;(useRecommendations as Mock).mockReturnValue(swr(over.recs))
}

beforeEach(() => vi.clearAllMocks())

describe('OverviewView', () => {
  it('cabeçalho: título e botão gerar recomendação', () => {
    setup()
    render(<OverviewView />)
    expect(screen.getByText('Visão geral')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Gerar recomendação/ })).toHaveAttribute('href', '/recomendacoes')
  })

  it('Forma: mostra TSB e leitura quando há form', () => {
    setup({ intel: { form: { metric_date: '2026-07-07', ctl: 60, atl: 45, tsb: 12 }, ftp_history: [], twin_seed: null } })
    render(<OverviewView />)
    expect(screen.getByText('+12')).toBeInTheDocument()
    expect(screen.getByText(/Fresco/)).toBeInTheDocument()
  })

  it('Forma: estado vazio quando não há form', () => {
    setup({ intel: { form: null, ftp_history: [], twin_seed: null } })
    render(<OverviewView />)
    expect(screen.getByText(/Sem dados de forma/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Importar treinos/ })).toHaveAttribute('href', '/importar')
  })

  it('Próximo treino: mostra o próximo planejado', () => {
    const today = new Date().toISOString().slice(0, 10)
    setup({ cal: { days: [{ date: today, planned: [{
      id: 'x', planned_date: today, name: 'Endurance Z2', workout_type: 'endurance',
      planned_duration_s: 5400, planned_tss: 70, description: null, structure: null, adjustment: null,
    }], completed: [], races: [] }], weeks: [] } })
    render(<OverviewView />)
    expect(screen.getByText('Endurance Z2')).toBeInTheDocument()
  })

  it('Próximo treino: vazio quando não há planejado', () => {
    setup({ cal: { days: [], weeks: [] } })
    render(<OverviewView />)
    expect(screen.getByText(/Nenhum treino planejado/)).toBeInTheDocument()
  })

  it('Semana + recomendação: totais e resumo', () => {
    const today = new Date().toISOString().slice(0, 10)
    setup({
      cal: { days: [], weeks: [{
        week_start: mondayOf(today), ctl: 50, atl: 40, tsb: 10,
        total_duration_s: 7200, total_tss: 123, total_distance_m: 60000, total_elevation_m: 0, total_kj: 0,
      }] },
      recs: [{
        id: 'r', target_date: null, kind: 'daily_workout', summary: 'Endurance longo hoje',
        physiological_objective: null, block_relation: null, rationale: null,
        adjust_if_tired: null, adjust_if_less_time: null, payload: null,
        risk_level: 'LOW', risk_flags: null, confidence: null, confidence_rationale: null,
        decision: 'PENDING', created_at: '2026-07-07T00:00:00Z', evidence: [],
      }],
    })
    render(<OverviewView />)
    expect(screen.getByText(/123/)).toBeInTheDocument()
    expect(screen.getByText(/Endurance longo hoje/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/overview`
Expected: FAIL — módulo `OverviewView` inexistente

- [ ] **Step 3: Implementar o componente e a página**

Criar `web/components/overview/OverviewView.tsx`:

```tsx
"use client";
import Link from 'next/link'
import { Brain } from 'lucide-react'
import { useIntelligence, useCalendar, useRecommendations } from '@/lib/hooks'
import { addDaysIso, currentWeekSummary, mostRecentRec, nextPlannedWorkout } from '@/lib/overview'
import { todayIso } from '@/lib/dateUtils'
import { mondayOf } from '@/lib/weekRange'
import { formReading, formTone, TONE_TEXT } from '@/lib/formState'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'

const r = Math.round
const SIGN = (n: number) => (n > 0 ? `+${n}` : String(n))

function hhmm(secs: number | null | undefined): string {
  if (!secs) return '—'
  const h = Math.floor(secs / 3600)
  const m = Math.round((secs % 3600) / 60)
  return h > 0 ? `${h}h${String(m).padStart(2, '0')}` : `${m}min`
}

function FormaCard() {
  const { data: intel, isLoading } = useIntelligence()
  const form = intel?.form ?? null
  return (
    <Card title="Forma (TSB)">
      {isLoading ? (
        <div className="h-16 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
      ) : form ? (
        <Link href="/forma-carga" className="block">
          <div className={`text-4xl font-extrabold ${TONE_TEXT[formTone(r(form.tsb))]}`}>{SIGN(r(form.tsb))}</div>
          <div className={`mt-1 text-sm font-semibold ${TONE_TEXT[formTone(r(form.tsb))]}`}>{formReading(r(form.tsb))}</div>
          <div className="mt-2 text-xs text-slate-500">Fitness {r(form.ctl)} · Fadiga {r(form.atl)}</div>
        </Link>
      ) : (
        <div className="text-sm text-slate-500">
          Sem dados de forma ainda.{' '}
          <Link href="/importar" className="font-medium text-blue-600 underline">Importar treinos</Link>
        </div>
      )}
    </Card>
  )
}

function ProximoTreinoCard() {
  const today = todayIso()
  const { data: cal, isLoading } = useCalendar(mondayOf(today), addDaysIso(today, 14))
  const next = nextPlannedWorkout(cal, today)
  return (
    <Card title="Próximo treino">
      {isLoading ? (
        <div className="h-16 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
      ) : next ? (
        <Link href="/plano" className="block">
          <div className="text-lg font-bold text-slate-800 dark:text-slate-100">{next.name}</div>
          <div className="mt-1 text-xs text-slate-500">
            {next.planned_date} · {next.workout_type} · {hhmm(next.planned_duration_s)}
            {next.planned_tss != null ? ` · TSS ${r(next.planned_tss)}` : ''}
          </div>
        </Link>
      ) : (
        <div className="text-sm text-slate-500">
          Nenhum treino planejado.{' '}
          <Link href="/recomendacoes" className="font-medium text-blue-600 underline">Gerar</Link>
        </div>
      )}
    </Card>
  )
}

function SemanaCard() {
  const today = todayIso()
  const { data: cal, isLoading: loadingCal } = useCalendar(mondayOf(today), addDaysIso(today, 14))
  const { data: recs, isLoading: loadingRecs } = useRecommendations()
  const week = currentWeekSummary(cal, today)
  const rec = mostRecentRec(recs)
  return (
    <Card title="Semana + recomendação">
      {loadingCal ? (
        <div className="h-16 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
      ) : (
        <div className="flex gap-6 text-sm">
          <div><div className="text-2xl font-bold text-slate-800 dark:text-slate-100">{week ? r(week.total_tss) : 0}</div><div className="text-xs text-slate-500">TSS</div></div>
          <div><div className="text-2xl font-bold text-slate-800 dark:text-slate-100">{hhmm(week?.total_duration_s ?? 0)}</div><div className="text-xs text-slate-500">tempo</div></div>
          <div><div className="text-2xl font-bold text-slate-800 dark:text-slate-100">{week ? r(week.total_distance_m / 1000) : 0}</div><div className="text-xs text-slate-500">km</div></div>
        </div>
      )}
      <div className="mt-3 border-t border-slate-100 pt-3 dark:border-slate-800">
        {loadingRecs ? (
          <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100 dark:bg-slate-800" />
        ) : rec ? (
          <Link href="/recomendacoes" className="block text-sm text-slate-600 hover:underline dark:text-slate-300">
            {rec.summary.length > 120 ? rec.summary.slice(0, 120) + '…' : rec.summary}
          </Link>
        ) : (
          <div className="text-sm text-slate-500">
            Nenhuma recomendação ainda.{' '}
            <Link href="/recomendacoes" className="font-medium text-blue-600 underline">Gerar</Link>
          </div>
        )}
      </div>
    </Card>
  )
}

export function OverviewView() {
  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100 sm:text-2xl">Visão geral</h1>
          <p className="text-sm text-slate-500">Seu painel de treino.</p>
        </div>
        <Link href="/recomendacoes">
          <Button><Brain className="h-4 w-4" /> Gerar recomendação</Button>
        </Link>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <FormaCard />
        <ProximoTreinoCard />
        <SemanaCard />
      </div>
    </div>
  )
}
```

Substituir todo o conteúdo de `web/app/(app)/page.tsx` por:

```tsx
import { OverviewView } from "@/components/overview/OverviewView";

export default function OverviewPage() {
  return <OverviewView />;
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run components/overview lib/__tests__/overview.test.ts`
Expected: todos verdes

- [ ] **Step 5: Commit**

```bash
git add web/components/overview web/app/\(app\)/page.tsx
git commit -m "feat(web): dashboard Visão geral com Forma, Próximo treino e Semana

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Landing unificada (login → sempre `/`)

**Files:**
- Modify: `web/app/(auth)/login/page.tsx` (2 redirects)
- Modify: `web/app/(auth)/login/__tests__/LoginPage.test.tsx` (ajuste do teste admin, se houver)

**Interfaces:**
- Consumes: nada novo.
- Produces: ambos os fluxos de login (email e Google) redirecionam para `/` independente do role.

- [ ] **Step 1: Escrever/ajustar o teste que falha**

Adicionar ao `web/app/(auth)/login/__tests__/LoginPage.test.tsx`, dentro do `describe` existente:

```tsx
  it('admin também vai para / (landing unificada)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonRes({ ok: true, role: 'ADMIN' })))
    render(<LoginPage />)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.c' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: /Entrar/ }))
    await waitFor(() => expect(push).toHaveBeenCalledWith('/'))
  })
```

Se já existir um teste afirmando `toHaveBeenCalledWith('/admin')`, trocar o alvo para `'/'`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run "app/(auth)/login"`
Expected: FAIL — o handler ainda manda admin para `/admin`

- [ ] **Step 3: Implementar**

Em `web/app/(auth)/login/page.tsx`, trocar as DUAS ocorrências de:

```tsx
      router.push(role === "ADMIN" ? "/admin" : "/");
```

por:

```tsx
      router.push("/");
```

(uma no `onSubmit` do login por email, outra no `onGoogle`). As variáveis `role` que ficarem sem uso devem ser removidas da desestruturação para o lint não reclamar — no `onSubmit`, trocar `const { role } = await res.json();` + push por apenas `router.push("/")` sem ler `role`; no `onGoogle`, idem (manter a leitura de `body.error` para o caso `invite_required`, remover só o uso de `role`).

- [ ] **Step 4: Rodar e ver passar (suíte web completa + lint)**

Run: `cd web && npx vitest run && npm run lint --if-present`
Expected: toda a suíte web verde; lint sem erros

- [ ] **Step 5: Commit**

```bash
git add web/app/\(auth\)/login
git commit -m "feat(web): landing unificada — todos entram na Visão geral

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
