# Frontend (Next.js) — Calendário + Detalhe do Treino — Implementation Plan (REVISADO)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Supersede:** Este plano substitui as Fases 2–7 (frontend) do plano `2026-06-29-spa-calendario-detalhe-treino.md`. As Tasks 1–3 (backend: `PlannedWorkoutRepository.list_between`, `GET /calendar`, `GET /workouts/{id}/streams`) **já estão concluídas e mergeadas nesta branch** — não refazer. O scaffold Vite (Task 4 antiga) foi **revertido**: o frontend usa o esqueleto **Next.js** já existente em `web/`.

**Goal:** Construir, no app Next.js existente em `web/`, a tela de **Calendário** (semana estilo TrainingPeaks: cards ricos, coluna Summary, marcadores de prova) e o **Detalhe do treino** (gráfico de intensidade, tabela Planned×Completed, Min/Avg/Max, breakdown de steps), consumindo `GET /calendar` e `GET /workouts/{id}/streams`.

**Architecture:** Reaproveita a fundação existente: auth por cookie httpOnly + proxy BFF (`web/app/api/proxy/[...path]/route.ts`), `apiFetch`/`jsonFetcher` (`web/lib/api.ts`), `AppShell`/`Sidebar`, UI kit (`web/components/ui/*`), Tailwind v4 + `theme/tokens.css`, SWR. A lógica pura nova vai em `web/lib/`; componentes em `web/components/calendar/` e `web/components/workout/`; a página `web/app/(app)/plano/page.tsx` (hoje stub `ComingSoon`) vira a tela de calendário.

**Tech Stack:** Next.js 15 (App Router) · React 19 · TypeScript strict · Tailwind v4 · SWR · lucide-react · uPlot (novo) · Vitest 3 + React Testing Library + jsdom.

## Global Constraints

- Trabalhar SOMENTE dentro de `web/`. Não tocar `backend/` nem o Streamlit em `frontend/`.
- REUTILIZAR a fundação existente — não recriar auth, proxy, shell ou UI kit. Buscar dados via `jsonFetcher(path)` (path sem `/api/v1`; o proxy injeta o Bearer do cookie e prefixa a base).
- TypeScript strict (o `tsconfig.json` do projeto já tem `strict`, `noUnusedLocals`, `noUnusedParameters`). Sem `any` solto.
- Componentes que usam hooks/estado/SWR começam com `"use client"`.
- Datas trafegam como ISO `YYYY-MM-DD`. Targets de potência no `structure` são frações do FTP (0.88 == 88%); watts = `fraction * ftp_watts`.
- Testes do front: `cd web && npm test` (Vitest run). Node do host: v24 / npm 11.
- Import alias do projeto: `@/...` → raiz de `web/` (configurado em `vitest.config.ts` e `tsconfig.json`).
- Estilo visual: seguir os prints do TrainingPeaks (referência de aceite) e o look existente (Card com barra-gradiente, dark mode, classes Tailwind como nos componentes atuais).
- Cada task: teste primeiro (TDD), rodar p/ falhar, implementar, rodar verde, commit.

---

### Task F1: Preparar dependências (uPlot + user-event) e validar o esqueleto

**Files:**
- Modify: `web/package.json`
- (gera `web/package-lock.json` atualizado)

**Interfaces:**
- Produces: `uplot` e `@testing-library/user-event` disponíveis; esqueleto Next.js continua buildando e com testes verdes.

- [ ] **Step 1: Add dependencies**

Em `web/package.json`, adicione em `dependencies`: `"uplot": "^1.6.31"`. Em `devDependencies`: `"@testing-library/user-event": "^14.5.2"`. Mantenha todo o resto.

- [ ] **Step 2: Install**

Run: `cd web && npm install`
Expected: instala sem erro; `package-lock.json` atualizado.

- [ ] **Step 3: Verify the skeleton still builds and tests pass**

Run: `cd web && npm test`
Expected: os testes existentes (`lib/__tests__/*`) passam — output pristine.
Run: `cd web && npx tsc --noEmit`
Expected: sem erros de tipo.

- [ ] **Step 4: Commit**

```bash
git add web/package.json web/package-lock.json
git commit -m "build(web): adiciona uplot + user-event ao esqueleto Next.js"
```

---

### Task F2: Lógica pura (`web/lib/`): format, zones, structure, compliance

**Files:**
- Create: `web/lib/format.ts`, `web/lib/zones.ts`, `web/lib/structure.ts`, `web/lib/compliance.ts`
- Test: `web/lib/__tests__/format.test.ts`, `web/lib/__tests__/zones.test.ts`, `web/lib/__tests__/structure.test.ts`, `web/lib/__tests__/compliance.test.ts`

**Interfaces:**
- Produces (todas funções puras, sem React):
  - `format`: `formatDuration(s: number | null): string` ("1:54:00"/"—"); `formatDistanceKm(m: number | null): string` ("30.0 km"/"—"); `formatTss(n: number | null): string` ("82 TSS"/"—").
  - `zones`: `pctToZone(pct: number): number` (1..7); `powerToZone(watts: number, ftp: number): number`; `ZONE_COLORS: Record<number,string>`; `zoneColor(zone: number): string`.
  - `structure`: tipos `StepEl`, `RepeatEl`, `WorkoutStructure`, `Segment`; `structureToSegments(structure: WorkoutStructure | null, ftpFallback?: number): Segment[]`; `structureToSteps(structure, ftpFallback?): Array<{ label; durationS; lowW; highW; zone }>`.
  - `compliance`: `type CardStatus = 'completed'|'planned'|'adjusted'|'rest'`; `cardStatus(input: { hasCompleted; hasAdjustment; isRest }): CardStatus`; `statusColor(status): string`.

- [ ] **Step 1: Write all four failing test files**

`web/lib/__tests__/format.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { formatDistanceKm, formatDuration, formatTss } from '@/lib/format'

describe('format', () => {
  it('duração h:mm:ss', () => {
    expect(formatDuration(6840)).toBe('1:54:00')
    expect(formatDuration(1500)).toBe('0:25:00')
    expect(formatDuration(null)).toBe('—')
  })
  it('distância km', () => {
    expect(formatDistanceKm(30000)).toBe('30.0 km')
    expect(formatDistanceKm(null)).toBe('—')
  })
  it('tss', () => {
    expect(formatTss(82)).toBe('82 TSS')
    expect(formatTss(null)).toBe('—')
  })
})
```

`web/lib/__tests__/zones.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { pctToZone, powerToZone, zoneColor } from '@/lib/zones'

describe('zones', () => {
  it('pctToZone limites', () => {
    expect(pctToZone(0.5)).toBe(1)
    expect(pctToZone(0.7)).toBe(2)
    expect(pctToZone(0.85)).toBe(3)
    expect(pctToZone(1.0)).toBe(4)
    expect(pctToZone(1.1)).toBe(5)
    expect(pctToZone(1.3)).toBe(6)
    expect(pctToZone(1.7)).toBe(7)
  })
  it('powerToZone usa o ftp', () => {
    expect(powerToZone(300, 300)).toBe(4)
    expect(powerToZone(150, 300)).toBe(1)
  })
  it('zoneColor é hex', () => {
    expect(zoneColor(4)).toMatch(/^#/)
  })
})
```

`web/lib/__tests__/structure.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { structureToSegments, structureToSteps } from '@/lib/structure'

const struct = {
  name: 'Z2 c/ Z4',
  ftp_watts: 300,
  elements: [
    { intensity: 'warmup', duration_s: 1500, target: { type: 'power_pct_ftp', low: 0.5, high: 0.65 } },
    { count: 2, steps: [
      { intensity: 'active', duration_s: 720, target: { type: 'power_pct_ftp', low: 0.95, high: 1.05 } },
      { intensity: 'rest', duration_s: 600, target: { type: 'power_pct_ftp', low: 0.5, high: 0.6 } },
    ] },
    { intensity: 'cooldown', duration_s: 900, target: { type: 'open' } },
  ],
}

describe('structureToSegments', () => {
  it('expande repeats e resolve watts', () => {
    const segs = structureToSegments(struct)
    expect(segs).toHaveLength(6)
    expect(segs[1]).toMatchObject({ durationS: 720, lowW: 285, highW: 315, zone: 4 })
    expect(segs[5]).toMatchObject({ intensity: 'cooldown', lowW: null, highW: null })
  })
  it('usa ftp fallback quando structure não tem', () => {
    const segs = structureToSegments({ elements: [{ intensity: 'active', duration_s: 60, target: { type: 'power_pct_ftp', low: 1, high: 1 } }] }, 200)
    expect(segs[0].lowW).toBe(200)
  })
})

describe('structureToSteps', () => {
  it('uma linha por step com rótulo', () => {
    const steps = structureToSteps(struct)
    expect(steps[0].label).toBe('Warm up')
    expect(steps).toHaveLength(6)
  })
})
```

`web/lib/__tests__/compliance.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { cardStatus, statusColor } from '@/lib/compliance'

describe('compliance', () => {
  it('prioridade rest > completed > adjusted > planned', () => {
    expect(cardStatus({ hasCompleted: true, hasAdjustment: true, isRest: true })).toBe('rest')
    expect(cardStatus({ hasCompleted: true, hasAdjustment: true, isRest: false })).toBe('completed')
    expect(cardStatus({ hasCompleted: false, hasAdjustment: true, isRest: false })).toBe('adjusted')
    expect(cardStatus({ hasCompleted: false, hasAdjustment: false, isRest: false })).toBe('planned')
  })
  it('cada status tem cor hex', () => {
    for (const s of ['completed', 'planned', 'adjusted', 'rest'] as const) {
      expect(statusColor(s)).toMatch(/^#/)
    }
  })
})
```

- [ ] **Step 2: Run to verify all fail**

Run: `cd web && npm test`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement the four modules**

`web/lib/format.ts`:
```ts
export function formatDuration(s: number | null): string {
  if (s == null) return '—'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}
export function formatDistanceKm(m: number | null): string {
  if (m == null) return '—'
  return `${(m / 1000).toFixed(1)} km`
}
export function formatTss(n: number | null): string {
  if (n == null) return '—'
  return `${Math.round(n)} TSS`
}
```

`web/lib/zones.ts`:
```ts
export function pctToZone(pct: number): number {
  if (pct <= 0.55) return 1
  if (pct <= 0.75) return 2
  if (pct <= 0.9) return 3
  if (pct <= 1.05) return 4
  if (pct <= 1.2) return 5
  if (pct <= 1.5) return 6
  return 7
}
export function powerToZone(watts: number, ftp: number): number {
  if (!ftp || ftp <= 0) return 1
  return pctToZone(watts / ftp)
}
export const ZONE_COLORS: Record<number, string> = {
  1: '#9ca3af', 2: '#3b82f6', 3: '#22c55e', 4: '#eab308', 5: '#f97316', 6: '#ef4444', 7: '#7c3aed',
}
export function zoneColor(zone: number): string {
  return ZONE_COLORS[zone] ?? ZONE_COLORS[1]
}
```

`web/lib/structure.ts`:
```ts
import { pctToZone } from '@/lib/zones'

export type StepEl = {
  intensity: string
  duration_s: number
  target?: { type: string; low?: number | null; high?: number | null }
  note?: string
}
export type RepeatEl = { count: number; steps: StepEl[] }
export type WorkoutStructure = { name?: string; elements?: Array<StepEl | RepeatEl>; ftp_watts?: number | null }
export type Segment = { durationS: number; lowW: number | null; highW: number | null; zone: number; intensity: string }

const LABELS: Record<string, string> = { warmup: 'Warm up', active: 'Active', rest: 'Recovery', cooldown: 'Cool Down' }

function flatten(structure: WorkoutStructure | null): StepEl[] {
  if (!structure?.elements) return []
  const out: StepEl[] = []
  for (const el of structure.elements) {
    if ('steps' in el && Array.isArray((el as RepeatEl).steps)) {
      const rep = el as RepeatEl
      for (let i = 0; i < rep.count; i++) out.push(...rep.steps)
    } else {
      out.push(el as StepEl)
    }
  }
  return out
}

function toSegment(step: StepEl, ftp: number): Segment {
  const t = step.target
  const isOpen = !t || t.type === 'open' || (t.low == null && t.high == null)
  const lowW = isOpen || t?.low == null ? null : Math.round(t.low * ftp)
  const highW = isOpen || t?.high == null ? null : Math.round(t.high * ftp)
  const mid = isOpen ? 0 : ((t?.low ?? t?.high ?? 0) + (t?.high ?? t?.low ?? 0)) / 2
  return { durationS: step.duration_s, lowW, highW, zone: isOpen ? 1 : pctToZone(mid), intensity: step.intensity }
}

export function structureToSegments(structure: WorkoutStructure | null, ftpFallback = 250): Segment[] {
  const ftp = structure?.ftp_watts ?? ftpFallback
  return flatten(structure).map((s) => toSegment(s, ftp))
}

export function structureToSteps(structure: WorkoutStructure | null, ftpFallback = 250) {
  const ftp = structure?.ftp_watts ?? ftpFallback
  return flatten(structure).map((s) => {
    const seg = toSegment(s, ftp)
    return { label: LABELS[s.intensity] ?? s.intensity, durationS: seg.durationS, lowW: seg.lowW, highW: seg.highW, zone: seg.zone }
  })
}
```

`web/lib/compliance.ts`:
```ts
export type CardStatus = 'completed' | 'planned' | 'adjusted' | 'rest'

export function cardStatus(input: { hasCompleted: boolean; hasAdjustment: boolean; isRest: boolean }): CardStatus {
  if (input.isRest) return 'rest'
  if (input.hasCompleted) return 'completed'
  if (input.hasAdjustment) return 'adjusted'
  return 'planned'
}

const COLORS: Record<CardStatus, string> = {
  completed: '#22c55e',
  planned: '#cbd5e1',
  adjusted: '#8b5cf6',
  rest: '#e2e8f0',
}
export function statusColor(status: CardStatus): string {
  return COLORS[status]
}
```

- [ ] **Step 4: Run to verify all pass**

Run: `cd web && npm test`
Expected: PASS (todas as suites, incluindo as existentes).

- [ ] **Step 5: Commit**

```bash
git add web/lib/format.ts web/lib/zones.ts web/lib/structure.ts web/lib/compliance.ts web/lib/__tests__/format.test.ts web/lib/__tests__/zones.test.ts web/lib/__tests__/structure.test.ts web/lib/__tests__/compliance.test.ts
git commit -m "feat(web): lib pura (format, zones, structure, compliance)"
```

---

### Task F3: Tipos + hooks SWR

**Files:**
- Create: `web/lib/types.ts`, `web/lib/hooks.ts`
- Test: `web/lib/__tests__/hooks.test.tsx`

**Interfaces:**
- Consumes: `jsonFetcher` (`web/lib/api.ts`), `WorkoutStructure` (`web/lib/structure.ts`), SWR.
- Produces:
  - `web/lib/types.ts`: `PlannedWorkout`, `CompletedWorkout`, `RaceMarker`, `CalendarDay`, `WeekSummary`, `CalendarResponse`, `WorkoutStreams` (espelham os schemas do backend; ver shapes abaixo).
  - `web/lib/hooks.ts` (`"use client"`): `useCalendar(start: string, end: string)` → `useSWR<CalendarResponse>`; `useWorkoutStreams(id: string | null)` → `useSWR<WorkoutStreams>` (key null quando id null → não busca).

- [ ] **Step 1: Write the types**

```ts
// web/lib/types.ts
import type { WorkoutStructure } from '@/lib/structure'

export type PlannedWorkout = {
  id: string; planned_date: string; name: string; workout_type: string
  planned_duration_s: number | null; planned_tss: number | null
  description: string | null; structure: WorkoutStructure | null
  adjustment: Record<string, unknown> | null
}
export type CompletedWorkout = {
  id: string; workout_date: string; name: string | null; workout_type: string
  duration_s: number | null; distance_m: number | null; tss: number | null
  intensity_factor: number | null; avg_power: number | null; normalized_power: number | null
  avg_hr: number | null; kj: number | null; elevation_gain_m: number | null; notes: string | null
}
export type RaceMarker = { id: string; name: string; race_date: string; days_until: number }
export type CalendarDay = { date: string; planned: PlannedWorkout[]; completed: CompletedWorkout[]; races: RaceMarker[] }
export type WeekSummary = {
  week_start: string; ctl: number | null; atl: number | null; tsb: number | null
  total_duration_s: number; total_tss: number; total_distance_m: number; total_elevation_m: number; total_kj: number
}
export type CalendarResponse = { days: CalendarDay[]; weeks: WeekSummary[] }
export type WorkoutStreams = {
  workout_id: string; n_points: number
  time_s: Array<number | null>; power: Array<number | null>; heart_rate: Array<number | null>
  cadence: Array<number | null>; altitude: Array<number | null>
}
```

- [ ] **Step 2: Write the failing hooks test**

```tsx
// web/lib/__tests__/hooks.test.tsx
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useCalendar } from '@/lib/hooks'

afterEach(() => vi.restoreAllMocks())

describe('useCalendar', () => {
  it('busca o proxy /calendar e retorna days', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ days: [{ date: '2026-05-12', planned: [], completed: [], races: [] }], weeks: [] }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    const { result } = renderHook(() => useCalendar('2026-05-11', '2026-05-17'))
    await waitFor(() => expect(result.current.data).toBeDefined())
    expect(result.current.data?.days[0].date).toBe('2026-05-12')
    // confirma que passou pelo proxy BFF
    const calledUrl = (globalThis.fetch as unknown as { mock: { calls: string[][] } }).mock.calls[0][0]
    expect(String(calledUrl)).toContain('/api/proxy/calendar')
  })
})
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd web && npm test`
Expected: FAIL — `@/lib/hooks` not found.

- [ ] **Step 4: Implement hooks**

```ts
// web/lib/hooks.ts
"use client";
import useSWR from 'swr'
import { jsonFetcher } from '@/lib/api'
import type { CalendarResponse, WorkoutStreams } from '@/lib/types'

export function useCalendar(start: string, end: string) {
  return useSWR<CalendarResponse>(`calendar?start=${start}&end=${end}`, jsonFetcher as (p: string) => Promise<CalendarResponse>)
}

export function useWorkoutStreams(id: string | null) {
  return useSWR<WorkoutStreams>(id ? `workouts/${id}/streams` : null, jsonFetcher as (p: string) => Promise<WorkoutStreams>)
}
```

> `jsonFetcher(path)` chama `apiFetch(path)` → `fetch('/api/proxy/' + path)`. O teste mocka `fetch` e confirma a URL do proxy.

- [ ] **Step 5: Run to verify it passes**

Run: `cd web && npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/lib/types.ts web/lib/hooks.ts web/lib/__tests__/hooks.test.tsx
git commit -m "feat(web): tipos da API + hooks SWR useCalendar/useWorkoutStreams"
```

---

### Task F4: Componentes do calendário (apresentacionais) — Card, Thumbnail, Summary

**Files:**
- Create: `web/components/calendar/IntensityThumbnail.tsx`, `web/components/calendar/WorkoutCard.tsx`, `web/components/calendar/SummaryColumn.tsx`
- Test: `web/components/calendar/__tests__/WorkoutCard.test.tsx`, `web/components/calendar/__tests__/SummaryColumn.test.tsx`

**Interfaces:**
- Consumes: `structureToSegments`/`Segment`, `zoneColor`, `cardStatus`/`statusColor`, `formatDuration`/`formatDistanceKm`/`formatTss`; tipos `PlannedWorkout`/`CompletedWorkout`/`WeekSummary`.
- Produces:
  - `IntensityThumbnail({ segments, height? }: { segments: Segment[]; height?: number })` — SVG de barras (largura ∝ duração, altura ∝ highW, cor = `zoneColor`).
  - `WorkoutCard({ planned, completed, onOpen }: { planned: PlannedWorkout | null; completed: CompletedWorkout | null; onOpen: (id: string) => void })` — botão clicável; faixa de status, ícone, título, duração(+✓), distância, TSS, descrição, thumbnail, badge "🤖 IA".
  - `SummaryColumn({ week }: { week: WeekSummary })` — Fitness/Fatigue/Form + totais.

- [ ] **Step 1: Write failing tests**

`web/components/calendar/__tests__/WorkoutCard.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'
import { WorkoutCard } from '@/components/calendar/WorkoutCard'

const planned: PlannedWorkout = {
  id: 'p1', planned_date: '2026-05-12', name: 'Z2 c/ Z4', workout_type: 'ENDURANCE',
  planned_duration_s: 6840, planned_tss: 103, description: 'Z2 com blocos de Z4',
  structure: { ftp_watts: 300, elements: [{ intensity: 'active', duration_s: 600, target: { type: 'power_pct_ftp', low: 1, high: 1 } }] },
  adjustment: null,
}
const completed: CompletedWorkout = {
  id: 'c1', workout_date: '2026-05-12', name: 'Z2 feito', workout_type: 'ENDURANCE',
  duration_s: 6800, distance_m: 51400, tss: 103, intensity_factor: 0.74, avg_power: 210,
  normalized_power: 222, avg_hr: 140, kj: 1434, elevation_gain_m: 300, notes: null,
}

describe('WorkoutCard', () => {
  it('mostra título, tss e duração; onOpen com id do executado', async () => {
    const onOpen = vi.fn()
    render(<WorkoutCard planned={planned} completed={completed} onOpen={onOpen} />)
    expect(screen.getByText('Z2 c/ Z4')).toBeInTheDocument()
    expect(screen.getByText('103 TSS')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button'))
    expect(onOpen).toHaveBeenCalledWith('c1')
  })
  it('badge IA quando há adjustment', () => {
    render(<WorkoutCard planned={{ ...planned, adjustment: { reason: 'x' } }} completed={null} onOpen={() => {}} />)
    expect(screen.getByText('🤖 IA')).toBeInTheDocument()
  })
})
```

`web/components/calendar/__tests__/SummaryColumn.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { WeekSummary } from '@/lib/types'
import { SummaryColumn } from '@/components/calendar/SummaryColumn'

const week: WeekSummary = {
  week_start: '2026-05-11', ctl: 12, atl: 45, tsb: -12,
  total_duration_s: 49440, total_tss: 767, total_distance_m: 242000, total_elevation_m: 4572, total_kj: 7240,
}

describe('SummaryColumn', () => {
  it('mostra CTL/ATL/TSB e totais', () => {
    render(<SummaryColumn week={week} />)
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('-12')).toBeInTheDocument()
    expect(screen.getByText(/767/)).toBeInTheDocument()
    expect(screen.getByText(/242/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd web && npm test`
Expected: FAIL.

- [ ] **Step 3: Implement IntensityThumbnail**

```tsx
// web/components/calendar/IntensityThumbnail.tsx
import type { Segment } from '@/lib/structure'
import { zoneColor } from '@/lib/zones'

export function IntensityThumbnail({ segments, height = 28 }: { segments: Segment[]; height?: number }) {
  const total = segments.reduce((a, s) => a + s.durationS, 0) || 1
  const maxW = Math.max(1, ...segments.map((s) => s.highW ?? 0))
  let x = 0
  return (
    <svg width="100%" height={height} viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" aria-hidden="true">
      {segments.map((s, i) => {
        const w = (s.durationS / total) * 100
        const h = ((s.highW ?? maxW * 0.4) / maxW) * height
        const rect = <rect key={i} x={x} y={height - h} width={w} height={h} fill={zoneColor(s.zone)} />
        x += w
        return rect
      })}
    </svg>
  )
}
```

- [ ] **Step 4: Implement WorkoutCard**

```tsx
// web/components/calendar/WorkoutCard.tsx
"use client";
import { Bike } from 'lucide-react'
import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'
import { cardStatus, statusColor } from '@/lib/compliance'
import { formatDistanceKm, formatDuration, formatTss } from '@/lib/format'
import { structureToSegments } from '@/lib/structure'
import { IntensityThumbnail } from '@/components/calendar/IntensityThumbnail'

export function WorkoutCard({
  planned, completed, onOpen,
}: { planned: PlannedWorkout | null; completed: CompletedWorkout | null; onOpen: (id: string) => void }) {
  const status = cardStatus({ hasCompleted: !!completed, hasAdjustment: !!planned?.adjustment, isRest: false })
  const title = planned?.name ?? completed?.name ?? 'Treino'
  const durationS = completed?.duration_s ?? planned?.planned_duration_s ?? null
  const tss = completed?.tss ?? planned?.planned_tss ?? null
  const openId = completed?.id ?? planned?.id ?? ''
  const segments = structureToSegments(planned?.structure ?? null)

  return (
    <button
      type="button"
      onClick={() => onOpen(openId)}
      className="w-full overflow-hidden rounded-lg border border-slate-200 bg-white text-left shadow-sm transition hover:shadow dark:border-slate-700 dark:bg-slate-900"
    >
      <div style={{ height: 4, background: statusColor(status) }} />
      <div className="space-y-1 p-2">
        <div className="flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-1 text-sm font-semibold text-slate-800 dark:text-slate-100">
            <Bike className="h-3.5 w-3.5 shrink-0 text-violet-500" />
            <span className="truncate">{title}</span>
          </span>
          {planned?.adjustment && <span className="shrink-0 text-xs font-medium text-violet-600 dark:text-violet-400">🤖 IA</span>}
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
          <span>{formatDuration(durationS)}{completed ? ' ✓' : ''}</span>
          {completed?.distance_m != null && <span>{formatDistanceKm(completed.distance_m)}</span>}
          <span className="font-medium">{formatTss(tss)}</span>
        </div>
        {planned?.description && <p className="line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{planned.description}</p>}
        {segments.length > 0 && <IntensityThumbnail segments={segments} />}
      </div>
    </button>
  )
}
```

- [ ] **Step 5: Implement SummaryColumn**

```tsx
// web/components/calendar/SummaryColumn.tsx
import type { WeekSummary } from '@/lib/types'
import { formatDuration } from '@/lib/format'

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <span className="font-medium text-slate-700 dark:text-slate-200">{value}</span>
    </div>
  )
}

export function SummaryColumn({ week }: { week: WeekSummary }) {
  const n = (v: number | null) => (v == null ? '—' : String(Math.round(v)))
  return (
    <div className="space-y-2 border-l border-slate-200 p-3 dark:border-slate-700">
      <div className="grid grid-cols-3 gap-1 text-center">
        {([['Fitness', week.ctl], ['Fatigue', week.atl], ['Form', week.tsb]] as const).map(([k, v]) => (
          <div key={k}>
            <div className="text-[10px] uppercase tracking-wide text-slate-400">{k}</div>
            <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">{n(v)}</div>
          </div>
        ))}
      </div>
      <Row label="Total Duration" value={formatDuration(week.total_duration_s)} />
      <Row label="Total TSS" value={n(week.total_tss)} />
      <Row label="Distance" value={`${(week.total_distance_m / 1000).toFixed(0)} km`} />
      <Row label="El. Gain" value={`${n(week.total_elevation_m)} m`} />
      <Row label="Work" value={`${n(week.total_kj)} kJ`} />
    </div>
  )
}
```

- [ ] **Step 6: Run to verify pass** — `cd web && npm test`. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/components/calendar/IntensityThumbnail.tsx web/components/calendar/WorkoutCard.tsx web/components/calendar/SummaryColumn.tsx web/components/calendar/__tests__/WorkoutCard.test.tsx web/components/calendar/__tests__/SummaryColumn.test.tsx
git commit -m "feat(web): WorkoutCard + thumbnail SVG + SummaryColumn"
```

---

### Task F5: Grade do calendário + página /plano

**Files:**
- Create: `web/lib/weekRange.ts`, `web/components/calendar/CalendarGrid.tsx`, `web/components/calendar/CalendarView.tsx`
- Modify: `web/app/(app)/plano/page.tsx`
- Test: `web/lib/__tests__/weekRange.test.ts`, `web/components/calendar/__tests__/CalendarGrid.test.tsx`

**Interfaces:**
- Consumes: `CalendarDay`/`WeekSummary`, `WorkoutCard`, `SummaryColumn`, `useCalendar`.
- Produces:
  - `weekRange`: `mondayOf(iso: string): string`; `weekDays(mondayIso: string): string[]` (7 ISO Seg→Dom).
  - `CalendarGrid({ days, weeks, onOpenWorkout })` — agrupa por semana (Seg–Dom), 7 colunas + `SummaryColumn`; marcadores de prova.
  - `CalendarView()` (`"use client"`) — calcula a semana atual (client), chama `useCalendar`, renderiza a grade, mantém estado do treino selecionado (passado à Task F6).
  - `plano/page.tsx` renderiza `<CalendarView/>`.

- [ ] **Step 1: Write failing weekRange test**

```ts
// web/lib/__tests__/weekRange.test.ts
import { describe, expect, it } from 'vitest'
import { mondayOf, weekDays } from '@/lib/weekRange'

describe('weekRange', () => {
  it('mondayOf retorna a segunda da semana', () => {
    expect(mondayOf('2026-05-13')).toBe('2026-05-11')
    expect(mondayOf('2026-05-11')).toBe('2026-05-11')
  })
  it('weekDays gera 7 dias Seg→Dom', () => {
    expect(weekDays('2026-05-11')).toEqual([
      '2026-05-11', '2026-05-12', '2026-05-13', '2026-05-14', '2026-05-15', '2026-05-16', '2026-05-17',
    ])
  })
})
```

- [ ] **Step 2: Run to verify it fails** — `cd web && npm test`. Expected: FAIL.

- [ ] **Step 3: Implement weekRange**

```ts
// web/lib/weekRange.ts
function parse(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}
function fmt(date: Date): string {
  return date.toISOString().slice(0, 10)
}
export function mondayOf(iso: string): string {
  const d = parse(iso)
  const dow = (d.getUTCDay() + 6) % 7
  d.setUTCDate(d.getUTCDate() - dow)
  return fmt(d)
}
export function weekDays(mondayIso: string): string[] {
  const start = parse(mondayIso)
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start)
    d.setUTCDate(start.getUTCDate() + i)
    return fmt(d)
  })
}
```

- [ ] **Step 4: Write failing CalendarGrid test**

```tsx
// web/components/calendar/__tests__/CalendarGrid.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CalendarDay, WeekSummary } from '@/lib/types'
import { CalendarGrid } from '@/components/calendar/CalendarGrid'

const days: CalendarDay[] = [
  { date: '2026-05-12', planned: [{ id: 'p1', planned_date: '2026-05-12', name: 'Z2', workout_type: 'ENDURANCE', planned_duration_s: 3600, planned_tss: 80, description: null, structure: null, adjustment: null }], completed: [], races: [{ id: 'r1', name: 'WOS Canastra', race_date: '2026-05-20', days_until: 8 }] },
]
const weeks: WeekSummary[] = [{ week_start: '2026-05-11', ctl: 12, atl: 45, tsb: -12, total_duration_s: 3600, total_tss: 80, total_distance_m: 0, total_elevation_m: 0, total_kj: 0 }]

describe('CalendarGrid', () => {
  it('renderiza card e marcador de prova', () => {
    render(<CalendarGrid days={days} weeks={weeks} onOpenWorkout={() => {}} />)
    expect(screen.getByText('Z2')).toBeInTheDocument()
    expect(screen.getByText(/WOS Canastra/)).toBeInTheDocument()
    expect(screen.getByText(/8 DAYS/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 5: Run to verify it fails** — Expected: FAIL.

- [ ] **Step 6: Implement CalendarGrid**

```tsx
// web/components/calendar/CalendarGrid.tsx
"use client";
import { Flag } from 'lucide-react'
import type { CalendarDay, WeekSummary } from '@/lib/types'
import { SummaryColumn } from '@/components/calendar/SummaryColumn'
import { WorkoutCard } from '@/components/calendar/WorkoutCard'
import { mondayOf, weekDays } from '@/lib/weekRange'

const DOW = ['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB', 'DOM']

function RaceFlag({ name, daysUntil }: { name: string; daysUntil: number }) {
  return (
    <div className="rounded border border-blue-300 bg-blue-50 p-1 text-xs text-blue-800 dark:border-blue-500/40 dark:bg-blue-500/10 dark:text-blue-300">
      <div className="font-semibold">{daysUntil} DAYS UNTIL EVENT</div>
      <div className="flex items-center gap-1 truncate"><Flag className="h-3 w-3" />{name}</div>
    </div>
  )
}

export function CalendarGrid({
  days, weeks, onOpenWorkout,
}: { days: CalendarDay[]; weeks: WeekSummary[]; onOpenWorkout: (id: string) => void }) {
  const byDate = new Map(days.map((d) => [d.date, d]))
  const mondays = [...new Set(days.map((d) => mondayOf(d.date)))].sort()
  const weekByStart = new Map(weeks.map((w) => [w.week_start, w]))

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[repeat(7,1fr)_220px] gap-2 text-[11px] font-semibold text-slate-400">
        {DOW.map((d) => <div key={d}>{d}</div>)}
        <div>SUMMARY</div>
      </div>
      {mondays.map((monday) => (
        <div key={monday} className="grid grid-cols-[repeat(7,1fr)_220px] gap-2">
          {weekDays(monday).map((iso) => {
            const day = byDate.get(iso)
            return (
              <div key={iso} className="min-h-32 space-y-1 rounded bg-slate-100/50 p-1 dark:bg-slate-800/40">
                <div className="text-[11px] text-slate-400">{Number(iso.slice(8, 10))}</div>
                {day?.races.map((r) => <RaceFlag key={r.id} name={r.name} daysUntil={r.days_until} />)}
                {day?.planned.map((p) => (
                  <WorkoutCard key={p.id} planned={p}
                    completed={day.completed.find((c) => c.workout_type === p.workout_type) ?? null}
                    onOpen={onOpenWorkout} />
                ))}
                {day?.completed
                  .filter((c) => !day.planned.some((p) => p.workout_type === c.workout_type))
                  .map((c) => <WorkoutCard key={c.id} planned={null} completed={c} onOpen={onOpenWorkout} />)}
              </div>
            )
          })}
          {weekByStart.get(monday)
            ? <SummaryColumn week={weekByStart.get(monday)!} />
            : <div className="border-l border-slate-200 dark:border-slate-700" />}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 7: Run to verify it passes** — Expected: PASS.

- [ ] **Step 8: Implement CalendarView + wire the page (no new test; covered manually/E2E)**

`web/components/calendar/CalendarView.tsx`:
```tsx
"use client";
import { useMemo, useState } from 'react'
import { useCalendar } from '@/lib/hooks'
import { mondayOf, weekDays } from '@/lib/weekRange'
import { CalendarGrid } from '@/components/calendar/CalendarGrid'
import { WorkoutDetailDrawer } from '@/components/workout/WorkoutDetailDrawer'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export function CalendarView() {
  const monday = useMemo(() => mondayOf(todayIso()), [])
  const days = useMemo(() => weekDays(monday), [monday])
  const { data, isLoading, error } = useCalendar(days[0], days[6])
  const [openId, setOpenId] = useState<string | null>(null)

  if (isLoading) return <p className="text-sm text-slate-500">Carregando…</p>
  if (error || !data) return <p className="text-sm text-red-600">Erro ao carregar o calendário.</p>

  const selected = openId
    ? data.days.flatMap((d) => [
        ...d.completed.filter((c) => c.id === openId).map((c) => ({
          completed: c, planned: d.planned.find((p) => p.workout_type === c.workout_type) ?? null,
        })),
        ...d.planned.filter((p) => p.id === openId && !d.completed.some((c) => c.id === openId))
          .map((p) => ({ completed: null, planned: p })),
      ])[0] ?? null
    : null

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">📅 Plano — Calendário</h1>
      <CalendarGrid days={data.days} weeks={data.weeks} onOpenWorkout={setOpenId} />
      {selected && (
        <WorkoutDetailDrawer planned={selected.planned} completed={selected.completed} onClose={() => setOpenId(null)} />
      )}
    </div>
  )
}
```

`web/app/(app)/plano/page.tsx` (substitui o ComingSoon):
```tsx
import { CalendarView } from '@/components/calendar/CalendarView'
export default function Page() {
  return <CalendarView />
}
```

> `CalendarView` importa `WorkoutDetailDrawer` (Task F6). Como a Task F6 vem depois, este passo deixa um import a resolver — implemente a Task F5 commitando weekRange + CalendarGrid (Steps 1–7) ANTES; faça os Steps 8–9 (CalendarView + page) JUNTO com a Task F6 OU crie um stub mínimo `WorkoutDetailDrawer` que F6 substitui. Para manter cada commit verde, crie primeiro o stub: `web/components/workout/WorkoutDetailDrawer.tsx` exportando `export function WorkoutDetailDrawer(_: { planned: unknown; completed: unknown; onClose: () => void }) { return null }`, e a Task F6 o implementa de fato.

- [ ] **Step 9: Commit**

```bash
git add web/lib/weekRange.ts web/lib/__tests__/weekRange.test.ts web/components/calendar/CalendarGrid.tsx web/components/calendar/__tests__/CalendarGrid.test.tsx web/components/calendar/CalendarView.tsx web/components/workout/WorkoutDetailDrawer.tsx "web/app/(app)/plano/page.tsx"
git commit -m "feat(web): grade do calendário + página /plano (drawer stub)"
```

- [ ] **Step 10: Verify build** — `cd web && npm test && npx tsc --noEmit`. Expected: PASS / sem erros de tipo.

---

### Task F6: Detalhe do treino — profile, tabela, steps, drawer

**Files:**
- Create: `web/components/workout/profileData.ts`, `web/components/workout/IntensityProfile.tsx`, `web/components/workout/StepsBreakdown.tsx`, `web/components/workout/PlannedCompletedTable.tsx`
- Modify: `web/components/workout/WorkoutDetailDrawer.tsx` (substitui o stub da F5)
- Test: `web/components/workout/__tests__/profileData.test.ts`, `web/components/workout/__tests__/StepsBreakdown.test.tsx`, `web/components/workout/__tests__/PlannedCompletedTable.test.tsx`

**Interfaces:**
- Consumes: `structureToSegments`/`structureToSteps`/`Segment`, `useWorkoutStreams`, `powerToZone`/`zoneColor`, `formatDuration`/`formatDistanceKm`, tipos `PlannedWorkout`/`CompletedWorkout`/`WorkoutStreams`.
- Produces:
  - `profileData`: `streamToBars(power: Array<number | null>, ftp: number): Array<{ value: number; zone: number }>`.
  - `IntensityProfile({ segments, streams, ftp })` — se `streams.power` tem dados, desenha o stream EXECUTADO via uPlot **colorido por zona** (use `streamToBars` para a zona de cada ponto e pinte por banda/segmento); senão desenha os `segments` planejados (SVG degraus). Sem dados → aviso. (RESOLUÇÃO DO CONTROLLER: `streamToBars` DEVE ser usado para a coloração por zona — não deixar helper órfão.)
  - `StepsBreakdown({ steps })` — "Label · N min @ X–Y W · Zona Z".
  - `PlannedCompletedTable({ planned, completed })` — Duração/Distância/TSS/IF/NP/Work/El.Gain em colunas Planned × Completed.
  - `WorkoutDetailDrawer({ planned, completed, onClose })` — drawer com cabeçalho, `IntensityProfile`, tabela, Min/Avg/Max, steps, painel de ajuste-IA.

- [ ] **Step 1: Write failing profileData test**

```ts
// web/components/workout/__tests__/profileData.test.ts
import { describe, expect, it } from 'vitest'
import { streamToBars } from '@/components/workout/profileData'

describe('streamToBars', () => {
  it('mapeia cada ponto à zona, null vira 0/zona1', () => {
    expect(streamToBars([null, 150, 300], 300)).toEqual([
      { value: 0, zone: 1 },
      { value: 150, zone: 1 },
      { value: 300, zone: 4 },
    ])
  })
})
```

- [ ] **Step 2: Write failing StepsBreakdown + PlannedCompletedTable tests**

`web/components/workout/__tests__/StepsBreakdown.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StepsBreakdown } from '@/components/workout/StepsBreakdown'

describe('StepsBreakdown', () => {
  it('renderiza rótulo, minutos, watts e zona', () => {
    render(<StepsBreakdown steps={[{ label: 'Warm up', durationS: 1500, lowW: 158, highW: 205, zone: 2 }]} />)
    expect(screen.getByText(/Warm up/)).toBeInTheDocument()
    expect(screen.getByText(/25 min/)).toBeInTheDocument()
    expect(screen.getByText(/158–205 W/)).toBeInTheDocument()
    expect(screen.getByText(/Zona 2/)).toBeInTheDocument()
  })
})
```

`web/components/workout/__tests__/PlannedCompletedTable.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'
import { PlannedCompletedTable } from '@/components/workout/PlannedCompletedTable'

const planned = { planned_duration_s: 6840, planned_tss: 103 } as PlannedWorkout
const completed = { duration_s: 6800, tss: 103, intensity_factor: 0.74, normalized_power: 222, kj: 1434, distance_m: 51400, elevation_gain_m: 300 } as CompletedWorkout

describe('PlannedCompletedTable', () => {
  it('mostra colunas planejado e executado', () => {
    render(<PlannedCompletedTable planned={planned} completed={completed} />)
    expect(screen.getByText('Planned')).toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.getByText('1:54:00')).toBeInTheDocument()
    expect(screen.getByText('0.74')).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run to verify all fail** — `cd web && npm test`. Expected: FAIL.

- [ ] **Step 4: Implement profileData**

```ts
// web/components/workout/profileData.ts
import { powerToZone } from '@/lib/zones'

export function streamToBars(power: Array<number | null>, ftp: number): Array<{ value: number; zone: number }> {
  return power.map((p) => {
    const v = p ?? 0
    return { value: v, zone: powerToZone(v, ftp) }
  })
}
```

- [ ] **Step 5: Implement StepsBreakdown**

```tsx
// web/components/workout/StepsBreakdown.tsx
type Step = { label: string; durationS: number; lowW: number | null; highW: number | null; zone: number }

export function StepsBreakdown({ steps }: { steps: Step[] }) {
  return (
    <ul className="space-y-2">
      {steps.map((s, i) => (
        <li key={i} className="text-sm text-slate-700 dark:text-slate-200">
          <span className="font-semibold">{s.label}</span>{' · '}
          <span>{Math.round(s.durationS / 60)} min</span>
          {s.lowW != null && s.highW != null && <span>{' @ '}{s.lowW}–{s.highW} W</span>}
          <span className="text-slate-500 dark:text-slate-400">{' · Zona '}{s.zone}</span>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 6: Implement PlannedCompletedTable**

```tsx
// web/components/workout/PlannedCompletedTable.tsx
import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'
import { formatDistanceKm, formatDuration } from '@/lib/format'

export function PlannedCompletedTable({ planned, completed }: { planned: PlannedWorkout | null; completed: CompletedWorkout | null }) {
  const num = (v: number | null | undefined, digits = 0) => (v == null ? '—' : v.toFixed(digits))
  const rows: Array<[string, string, string]> = [
    ['Duration', formatDuration(planned?.planned_duration_s ?? null), formatDuration(completed?.duration_s ?? null)],
    ['Distance', '—', formatDistanceKm(completed?.distance_m ?? null)],
    ['TSS', num(planned?.planned_tss), num(completed?.tss)],
    ['IF', '—', num(completed?.intensity_factor ?? null, 2)],
    ['NP', '—', completed?.normalized_power != null ? `${Math.round(completed.normalized_power)} W` : '—'],
    ['Work', '—', completed?.kj != null ? `${Math.round(completed.kj)} kJ` : '—'],
    ['El. Gain', '—', completed?.elevation_gain_m != null ? `${Math.round(completed.elevation_gain_m)} m` : '—'],
  ]
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-slate-400">
          <th className="font-normal"></th><th className="font-normal">Planned</th><th className="font-normal">Completed</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([k, p, c]) => (
          <tr key={k} className="border-t border-slate-100 dark:border-slate-800">
            <td className="py-1 text-slate-500 dark:text-slate-400">{k}</td>
            <td className="py-1 text-slate-700 dark:text-slate-200">{p}</td>
            <td className="py-1 font-medium text-slate-800 dark:text-slate-100">{c}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
```

- [ ] **Step 7: Implement IntensityProfile (planejado SVG + executado uPlot colorido por zona)**

```tsx
// web/components/workout/IntensityProfile.tsx
"use client";
import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { WorkoutStreams } from '@/lib/types'
import type { Segment } from '@/lib/structure'
import { zoneColor } from '@/lib/zones'
import { streamToBars } from '@/components/workout/profileData'

function PlannedSvg({ segments }: { segments: Segment[] }) {
  const total = segments.reduce((a, s) => a + s.durationS, 0) || 1
  const maxW = Math.max(1, ...segments.map((s) => s.highW ?? 0))
  let x = 0
  return (
    <svg width="100%" height={120} viewBox="0 0 100 120" preserveAspectRatio="none" role="img" aria-label="Perfil planejado">
      {segments.map((s, i) => {
        const w = (s.durationS / total) * 100
        const h = ((s.highW ?? maxW * 0.4) / maxW) * 120
        const rect = <rect key={i} x={x} y={120 - h} width={w} height={h} fill={zoneColor(s.zone)} />
        x += w
        return rect
      })}
    </svg>
  )
}

function StreamPlot({ streams, ftp }: { streams: WorkoutStreams; ftp: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const bars = streamToBars(streams.power, ftp)
    const xs = bars.map((_, i) => i)
    const ys = bars.map((b) => b.value)
    // Coloração por zona: pinta cada ponto com a cor da sua zona via paths por-ponto.
    const opts: uPlot.Options = {
      width: ref.current.clientWidth || 600,
      height: 150,
      scales: { x: { time: false } },
      legend: { show: false },
      axes: [{ show: false }, { size: 34 }],
      series: [
        {},
        {
          stroke: '#1d4ed8',
          width: 1,
          paths: (u, sidx, i0, i1) => {
            const p = new Path2D()
            const ctx = (u as unknown as { ctx: CanvasRenderingContext2D }).ctx
            for (let i = i0; i <= i1; i++) {
              const xv = u.valToPos(u.data[0][i] as number, 'x', true)
              const yv = u.valToPos(u.data[sidx][i] as number, 'y', true)
              const y0 = u.valToPos(0, 'y', true)
              ctx.beginPath()
              ctx.strokeStyle = zoneColor(bars[i].zone)
              ctx.moveTo(xv, y0)
              ctx.lineTo(xv, yv)
              ctx.stroke()
            }
            return p
          },
        },
      ],
    }
    const plot = new uPlot(opts, [xs, ys], ref.current)
    return () => plot.destroy()
  }, [streams, ftp])
  return <div ref={ref} aria-label="Perfil executado" />
}

export function IntensityProfile({ segments, streams, ftp }: { segments: Segment[]; streams?: WorkoutStreams | null; ftp: number }) {
  if (streams && streams.power.length > 0) return <StreamPlot streams={streams} ftp={ftp} />
  if (segments.length > 0) return <PlannedSvg segments={segments} />
  return <div className="text-xs text-slate-400">Sem dados de intensidade.</div>
}
```

> O perfil EXECUTADO é colorido por zona usando `streamToBars` (resolve o helper órfão). uPlot é validado manualmente/E2E (não testar canvas no jsdom); o teste cobre `streamToBars`.

- [ ] **Step 8: Implement WorkoutDetailDrawer (substitui o stub da F5)**

```tsx
// web/components/workout/WorkoutDetailDrawer.tsx
"use client";
import { X } from 'lucide-react'
import { useWorkoutStreams } from '@/lib/hooks'
import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'
import { structureToSegments, structureToSteps } from '@/lib/structure'
import { IntensityProfile } from '@/components/workout/IntensityProfile'
import { PlannedCompletedTable } from '@/components/workout/PlannedCompletedTable'
import { StepsBreakdown } from '@/components/workout/StepsBreakdown'

export function WorkoutDetailDrawer({
  planned, completed, onClose,
}: { planned: PlannedWorkout | null; completed: CompletedWorkout | null; onClose: () => void }) {
  const { data: streams } = useWorkoutStreams(completed?.id ?? null)
  const ftp = planned?.structure?.ftp_watts ?? 250
  const segments = structureToSegments(planned?.structure ?? null, ftp)
  const steps = structureToSteps(planned?.structure ?? null, ftp)
  const title = planned?.name ?? completed?.name ?? 'Treino'

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <aside
        className="h-full w-full max-w-2xl overflow-y-auto bg-white p-5 shadow-xl dark:bg-slate-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Fechar" className="rounded p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
            <X className="h-5 w-5" />
          </button>
        </div>
        <IntensityProfile segments={segments} streams={streams} ftp={ftp} />
        {planned?.adjustment && (
          <div className="my-3 rounded border border-violet-200 bg-violet-50 p-2 text-sm text-violet-800 dark:border-violet-500/40 dark:bg-violet-500/10 dark:text-violet-300">
            🤖 Treino ajustado pela IA. Valores efetivos refletem o ajuste do dia.
          </div>
        )}
        <div className="my-4"><PlannedCompletedTable planned={planned} completed={completed} /></div>
        {completed && (
          <div className="my-4 grid grid-cols-3 gap-2 text-sm text-slate-700 dark:text-slate-200">
            <div><div className="text-xs text-slate-400">Avg Power</div><div>{completed.avg_power != null ? `${Math.round(completed.avg_power)} W` : '—'}</div></div>
            <div><div className="text-xs text-slate-400">Avg HR</div><div>{completed.avg_hr != null ? `${Math.round(completed.avg_hr)} bpm` : '—'}</div></div>
            <div><div className="text-xs text-slate-400">NP</div><div>{completed.normalized_power != null ? `${Math.round(completed.normalized_power)} W` : '—'}</div></div>
          </div>
        )}
        {steps.length > 0 && (
          <div className="my-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">Workout Details</h3>
            <StepsBreakdown steps={steps} />
          </div>
        )}
        {(planned?.description || completed?.notes) && (
          <p className="my-2 text-sm text-slate-600 dark:text-slate-300">{planned?.description ?? completed?.notes}</p>
        )}
      </aside>
    </div>
  )
}
```

- [ ] **Step 9: Run to verify pass + types** — `cd web && npm test && npx tsc --noEmit`. Expected: PASS / sem erros.

- [ ] **Step 10: Commit**

```bash
git add web/components/workout/
git commit -m "feat(web): detalhe do treino (perfil por zona, tabela, steps, drawer)"
```

---

### Task F7: Containerizar a app Next.js (serviço docker `web`)

**Files:**
- Create: `web/Dockerfile`, `web/.dockerignore`
- Modify: `web/next.config.mjs` (output standalone), `docker-compose.yml` (serviço `web`)

**Interfaces:**
- Produces: imagem Next.js (standalone) servindo a app, com `API_BASE_URL` apontando para o serviço `api`, ao lado do Streamlit.

- [ ] **Step 1: Enable standalone output**

Em `web/next.config.mjs`, garanta `output: 'standalone'` no objeto de config exportado (preserve o resto). Se já existir, não duplicar.

- [ ] **Step 2: Create Dockerfile**

```dockerfile
# web/Dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim AS run
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

- [ ] **Step 3: Create .dockerignore**

```
# web/.dockerignore
node_modules
.next
```

- [ ] **Step 4: Add compose service**

Em `docker-compose.yml`, adicione ao lado de `frontend` (Streamlit), na mesma rede/indentação do serviço `api`:

```yaml
  web:
    build: ./web
    environment:
      - API_BASE_URL=http://api:8000/api/v1
    ports:
      - "3000:3000"
    depends_on:
      - api
```

- [ ] **Step 5: Build and smoke-check**

Run: `docker compose build web && docker compose up -d web && curl -sI http://localhost:3000/login | head -1`
Expected: HTTP 200; a tela de login Next.js carrega em http://localhost:3000.

- [ ] **Step 6: Commit**

```bash
git add web/Dockerfile web/.dockerignore web/next.config.mjs docker-compose.yml
git commit -m "feat(web): containeriza a app Next.js (standalone) ao lado do Streamlit"
```

---

## Verificação final do ciclo (frontend)

- `cd web && npm test` → todas as suites verdes (lib pura + hooks + componentes).
- `cd web && npx tsc --noEmit` → sem erros de tipo.
- Manual: `docker compose up -d --build api web` → abrir http://localhost:3000, logar com o atleta de validação, ir em **Plano**, ver a semana com cards + coluna Summary + marcadores de prova; clicar num treino e ver o detalhe com gráfico (planejado em degraus / executado por zona), tabela Planned×Completed, Min/Avg/Max e breakdown de steps.

## Self-review (cobertura)

- Adoção da fundação Next.js (auth/proxy/shell/UI) — reutilizada, não recriada (Global Constraints). ✓
- lib pura (format/zones/structure/compliance) → F2. ✓
- tipos + hooks SWR → F3. ✓
- calendário (cards, thumbnail, summary, grade, provas, IA badge, página) → F4, F5. ✓
- detalhe (perfil planejado+executado-por-zona, tabela, min/avg/max, steps, drawer, painel IA) → F6. `streamToBars` agora É usado (resolve o helper órfão do plano Vite). ✓
- deployment Next.js (standalone + compose) → F7. ✓
- Backend (Tasks 1–3) já concluído — fora deste plano. ✓
- Linha Metrics/Sleep diária: deferida (sem fonte de dado), como no spec. ✓
