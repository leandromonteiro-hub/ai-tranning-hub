# Botão "Gerar Plano" + Horizonte das Bandeiras — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O atleta gera o plano (com expansão diária) por um botão na página Provas; regenerar substitui o plano anterior da mesma prova; bandeiras de contagem só aparecem a ≤30 dias da prova.

**Architecture:** Substituição vive no `POST /plans/generate` (arquiva plano ativo do mesmo `target_race_id` e apaga os treinos FUTUROS dele). O botão na ProvasView encadeia generate→expand. O horizonte é filtro visual no CalendarGrid via helper puro.

**Tech Stack:** FastAPI + SQLAlchemy, Next.js 15 + SWR, vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-02-gerar-plano-ui-design.md`

## Global Constraints

- Backend NÃO roda no host — suíte na VM Contabo via comando `!` do usuário:
  `tar -cz -C /c/projetos/treinador-ciclismo/backend . | ssh -i ~/.ssh/id_ed25519_aath_vps -o IdentitiesOnly=yes root@62.171.128.103 "tar -xz -C /opt/aath-test/backend && docker run --rm -v /opt/aath-test/backend:/app -w /app aath-test:latest pytest -q 2>&1 | tail -15"`
- Web no host: `cd web && npx vitest run` · `npx tsc --noEmit`.
- Horizonte da bandeira: **30 dias** (constante no helper `showRaceFlag`).
- Nome do plano gerado: `Plano — {nome da prova}`.
- Textos de UI em português. Branch: `feat/gerar-plano-ui` (existe, tem a spec).

---

### Task 1: Backend — generate substitui plano da mesma prova

**Files:**
- Modify: `backend/app/api/routes/plans.py:42-55` (rota `generate`) e o import de `sqlalchemy` (linha 9)
- Test: `backend/app/tests/test_api/test_plan_generate_replace.py` (novo)

**Interfaces:**
- Consumes: `TrainingPlan.target_race_id` (já existe), `WorkoutPlanned.source_plan_id`.
- Produces: `POST /plans/generate` com `target_race_id` arquiva plano ativo anterior do mesmo alvo e apaga seus `WorkoutPlanned` com `planned_date >= hoje`. Sem `target_race_id`: comportamento atual.

- [ ] **Step 1: Write the failing test** — arquivo novo, copiando as fixtures locais de `test_plan_expand.py` (env/_token, mesmo padrão SQLite in-memory):

```python
"""POST /plans/generate substitui o plano ativo da mesma prova (spec 2026-08-02)."""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role, WorkoutType
from app.models.race import Race
from app.models.training_plan import TrainingPlan
from app.models.workout import WorkoutPlanned

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        ath = Athlete(email="a@example.com", hashed_password=hash_password("pw12345678"),
                      full_name="A", role=Role.ATHLETE, tenant_id="ta")
        s.add(ath)
        await s.flush()
        aid = ath.id
        await s.commit()

    async def _override_get_db():
        async with maker() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield SimpleNamespace(client=c, maker=maker, aid=aid)
    app.dependency_overrides.clear()
    await engine.dispose()


async def _auth(client):
    r = await client.post("/api/v1/auth/login",
                          data={"username": "a@example.com", "password": "pw12345678"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_regenerar_substitui_plano_da_mesma_prova(env):
    headers = await _auth(env.client)
    race_date = date.today() + timedelta(days=28)
    async with env.maker() as s:
        rc = Race(athlete_id=env.aid, name="Epic", race_date=race_date, priority="B")
        s.add(rc)
        await s.flush()
        race_id = str(rc.id)
        await s.commit()

    body = {"name": "Plano — Epic", "race_date": race_date.isoformat(),
            "target_race_id": race_id, "priority": "B"}
    r1 = await env.client.post("/api/v1/plans/generate", json=body, headers=headers)
    assert r1.status_code == 201, r1.text
    plan1 = r1.json()["id"]
    ex = await env.client.post(f"/api/v1/plans/{plan1}/expand", headers=headers)
    assert ex.status_code == 201, ex.text

    # Treino PASSADO do plano 1 (histórico) — não pode ser apagado na regeneração.
    async with env.maker() as s:
        s.add(WorkoutPlanned(athlete_id=env.aid, source_plan_id=plan1,
                             planned_date=date.today() - timedelta(days=1),
                             name="Antigo", workout_type=WorkoutType.ENDURANCE,
                             planned_tss=50, planned_duration_s=3600))
        await s.commit()

    r2 = await env.client.post("/api/v1/plans/generate", json=body, headers=headers)
    assert r2.status_code == 201, r2.text
    plan2 = r2.json()["id"]
    assert plan2 != plan1

    async with env.maker() as s:
        old = (await s.execute(select(TrainingPlan).where(TrainingPlan.id == plan1))).scalar_one()
        assert old.deleted_at is not None  # arquivado

        rows = (await s.execute(select(WorkoutPlanned).where(
            WorkoutPlanned.source_plan_id == plan1))).scalars().all()
        # Só sobra o treino passado; os futuros do plano antigo foram apagados.
        assert [w.name for w in rows] == ["Antigo"]


async def test_generate_sem_target_race_nao_arquiva_nada(env):
    headers = await _auth(env.client)
    race_date = date.today() + timedelta(days=28)
    body = {"name": "Plano avulso", "race_date": race_date.isoformat()}
    r1 = await env.client.post("/api/v1/plans/generate", json=body, headers=headers)
    r2 = await env.client.post("/api/v1/plans/generate", json=body, headers=headers)
    assert r1.status_code == 201 and r2.status_code == 201
    async with env.maker() as s:
        plans = (await s.execute(select(TrainingPlan).where(
            TrainingPlan.deleted_at.is_(None)))).scalars().all()
        assert len(plans) == 2  # dois planos ativos, nenhum arquivado
```

- [ ] **Step 2: Verify it fails** — estático (sem Python no host): a rota `generate` atual (plans.py:42-55) não toca planos existentes, então `old.deleted_at` seria `None` e os futuros do plano 1 continuariam existindo ⇒ os dois asserts centrais falham.

- [ ] **Step 3: Write minimal implementation** em `backend/app/api/routes/plans.py`:

Import (linha 9): `from sqlalchemy import delete, select`

Na rota `generate`, antes de `plan = await generate_plan(...)`:

```python
    # Regenerar substitui: arquiva o plano ativo da mesma prova e apaga os
    # treinos FUTUROS dele (os passados ficam para o histórico de compliance).
    if body.target_race_id is not None:
        old_plans = (await db.execute(
            select(TrainingPlan).where(
                TrainingPlan.athlete_id == ctx.athlete_id,
                TrainingPlan.target_race_id == body.target_race_id,
                TrainingPlan.deleted_at.is_(None),
            )
        )).scalars().all()
        for old in old_plans:
            old.deleted_at = datetime.now(timezone.utc)
            db.add(old)
            await db.execute(
                delete(WorkoutPlanned).where(
                    WorkoutPlanned.athlete_id == ctx.athlete_id,
                    WorkoutPlanned.source_plan_id == old.id,
                    WorkoutPlanned.planned_date >= date.today(),
                )
            )
```

(`date`, `datetime`, `timezone`, `TrainingPlan`, `WorkoutPlanned` já são importados no arquivo.)

- [ ] **Step 4: Verify** — leitura confere; suíte roda na VM na Task 5.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/plans.py backend/app/tests/test_api/test_plan_generate_replace.py
git commit -m "feat(plans): regenerar substitui o plano ativo da mesma prova"
```

---

### Task 2: Web — helpers `showRaceFlag` e `isFutureRace`

**Files:**
- Modify: `web/lib/races.ts`
- Test: `web/lib/__tests__/races.test.ts` (append)

**Interfaces:**
- Produces: `showRaceFlag(daysUntil: number): boolean` (Task 3) e
  `isFutureRace(race: { race_date: string; end_date?: string | null }, todayIso: string): boolean` (Task 4).

- [ ] **Step 1: Write the failing tests** (append em `races.test.ts`; acrescentar `isFutureRace, showRaceFlag` ao import de `@/lib/races`):

```ts
describe('showRaceFlag', () => {
  it('esconde prova a mais de 30 dias', () => {
    expect(showRaceFlag(31)).toBe(false)
    expect(showRaceFlag(60)).toBe(false)
  })
  it('mostra a 30 dias ou menos, incluindo durante a prova', () => {
    expect(showRaceFlag(30)).toBe(true)
    expect(showRaceFlag(1)).toBe(true)
    expect(showRaceFlag(0)).toBe(true)
    expect(showRaceFlag(-2)).toBe(true)
  })
})

describe('isFutureRace', () => {
  it('prova de amanhã é futura; de ontem não é', () => {
    expect(isFutureRace({ race_date: '2026-08-03', end_date: null }, '2026-08-02')).toBe(true)
    expect(isFutureRace({ race_date: '2026-08-01', end_date: null }, '2026-08-02')).toBe(false)
  })
  it('prova multi-dia em andamento ainda conta como futura', () => {
    expect(isFutureRace({ race_date: '2026-08-01', end_date: '2026-08-03' }, '2026-08-02')).toBe(true)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run lib/__tests__/races.test.ts`
Expected: FAIL — funções não exportadas.

- [ ] **Step 3: Write minimal implementation** (append em `web/lib/races.ts`):

```ts
/** Bandeira de contagem só entra no radar a 30 dias da prova (<=0 = durante). */
const RACE_FLAG_HORIZON_DAYS = 30
export function showRaceFlag(daysUntil: number): boolean {
  return daysUntil <= RACE_FLAG_HORIZON_DAYS
}

/** Prova ainda relevante: o último dia (end_date ?? race_date) não passou. */
export function isFutureRace(
  race: { race_date: string; end_date?: string | null },
  todayIso: string,
): boolean {
  return (race.end_date ?? race.race_date) >= todayIso
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run lib/__tests__/races.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/lib/races.ts web/lib/__tests__/races.test.ts
git commit -m "feat(web): helpers showRaceFlag (horizonte 30d) e isFutureRace"
```

---

### Task 3: Web — CalendarGrid filtra bandeiras pelo horizonte

**Files:**
- Modify: `web/components/calendar/CalendarGrid.tsx:40` (render das races)
- Test: `web/components/calendar/__tests__/CalendarGrid.test.tsx` (append)

**Interfaces:**
- Consumes: `showRaceFlag` (Task 2).

- [ ] **Step 1: Write the failing test** (append no `describe('CalendarGrid')`):

```tsx
  it('não mostra bandeira de prova a mais de 30 dias', () => {
    const farDays: CalendarDay[] = [
      {
        date: '2026-05-12', planned: [], completed: [],
        races: [{ id: 'r9', name: 'Cape Epic', race_date: '2026-07-20', days_until: 69 }],
      },
    ]
    render(<CalendarGrid days={farDays} weeks={[]} onOpenWorkout={() => {}} />)
    expect(screen.queryByText(/Cape Epic/)).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run components/calendar/__tests__/CalendarGrid.test.tsx`
Expected: FAIL — hoje a bandeira renderiza em qualquer distância.

- [ ] **Step 3: Write minimal implementation** em `CalendarGrid.tsx`:

Import: `import { showRaceFlag } from '@/lib/races'`

Linha 40, de:
```tsx
{day?.races.map((r) => <RaceFlag key={r.id} name={r.name} daysUntil={r.days_until} />)}
```
para:
```tsx
{day?.races.filter((r) => showRaceFlag(r.days_until)).map((r) => <RaceFlag key={r.id} name={r.name} daysUntil={r.days_until} />)}
```

- [ ] **Step 4: Run tests to verify they pass** (o teste existente de 8 dias e o de "DIA 2 DA PROVA" continuam verdes)

Run: `cd web && npx vitest run components/calendar/__tests__/CalendarGrid.test.tsx`
Expected: PASS (3 testes)

- [ ] **Step 5: Commit**

```bash
git add web/components/calendar/CalendarGrid.tsx web/components/calendar/__tests__/CalendarGrid.test.tsx
git commit -m "feat(web): bandeira de prova só a 30 dias ou durante a prova"
```

---

### Task 4: Web — botão "Gerar plano" na página Provas

**Files:**
- Modify: `web/components/provas/ProvasView.tsx`
- Test: `web/components/provas/__tests__/ProvasView.test.tsx` (append)

**Interfaces:**
- Consumes: `isFutureRace` (Task 2); `apiFetch` (existente); endpoints `plans/generate` e `plans/{id}/expand` (Task 1).

- [ ] **Step 1: Write the failing tests** (append no `describe('ProvasView')`; o arquivo já importa `fireEvent` e `SWRConfig`):

```tsx
  it('botão Gerar plano dispara generate + expand e mostra sucesso', async () => {
    const race = {
      id: 'r1', athlete_id: 'a', name: 'Cape Epic', race_date: '2099-03-21',
      end_date: '2099-03-28', priority: 'A', discipline: null, location: null,
      distance_km: null, elevation_gain_m: null, notes: null, created_at: '',
    }
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
      const u = String(url)
      if (u.endsWith('/plans/generate')) {
        return new Response(JSON.stringify({ id: 'p1' }), { status: 201, headers: { 'Content-Type': 'application/json' } })
      }
      if (u.endsWith('/plans/p1/expand')) {
        return new Response(JSON.stringify({ days: 193, tss_total: 1, start: '', end: '' }), { status: 201, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response(JSON.stringify([race]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <ProvasView />
      </SWRConfig>,
    )
    const btn = await screen.findByRole('button', { name: /Gerar plano/ })
    fireEvent.click(btn)
    await waitFor(() => expect(screen.getByText(/Plano gerado: 193 treinos/)).toBeInTheDocument())
    const urls = spy.mock.calls.map(([u]) => String(u))
    expect(urls.some((u) => u.endsWith('/plans/generate'))).toBe(true)
    expect(urls.some((u) => u.endsWith('/plans/p1/expand'))).toBe(true)
    const genCall = spy.mock.calls.find(([u]) => String(u).endsWith('/plans/generate'))!
    expect(JSON.parse(String(genCall[1]!.body))).toMatchObject({
      name: 'Plano — Cape Epic', race_date: '2099-03-21', target_race_id: 'r1', priority: 'A',
    })
  })

  it('prova passada não mostra o botão', async () => {
    const past = {
      id: 'r2', athlete_id: 'a', name: 'WOS', race_date: '2020-01-01',
      end_date: null, priority: 'B', discipline: null, location: null,
      distance_km: null, elevation_gain_m: null, notes: null, created_at: '',
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([past]), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <ProvasView />
      </SWRConfig>,
    )
    await screen.findByText('WOS')
    expect(screen.queryByRole('button', { name: /Gerar plano/ })).not.toBeInTheDocument()
  })

  it('falha no generate mostra erro na linha', async () => {
    const race = {
      id: 'r3', athlete_id: 'a', name: 'Epic', race_date: '2099-08-29',
      end_date: null, priority: 'B', discipline: null, location: null,
      distance_km: null, elevation_gain_m: null, notes: null, created_at: '',
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (String(url).endsWith('/plans/generate')) return new Response('{}', { status: 500 })
      return new Response(JSON.stringify([race]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <ProvasView />
      </SWRConfig>,
    )
    fireEvent.click(await screen.findByRole('button', { name: /Gerar plano/ }))
    await waitFor(() => expect(screen.getByText(/Não foi possível gerar o plano/)).toBeInTheDocument())
  })
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run components/provas`
Expected: FAIL — não existe botão "Gerar plano".

- [ ] **Step 3: Write minimal implementation** em `ProvasView.tsx`:

Imports: acrescentar `isFutureRace` ao import de `@/lib/races`; `import { todayIso } from '@/lib/dateUtils'`; `import type { Race } from '@/lib/types'`.

Estado (junto dos demais):
```tsx
  const [gen, setGen] = useState<Record<string, { status: 'busy' | 'ok' | 'error'; days?: number }>>({})
```

Função (depois de `submit`):
```tsx
  async function generatePlan(r: Race) {
    setGen((g) => ({ ...g, [r.id]: { status: 'busy' } }))
    try {
      const res = await apiFetch('plans/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: `Plano — ${r.name}`,
          race_date: r.race_date,
          target_race_id: r.id,
          priority: r.priority,
        }),
      })
      if (!res.ok) throw new Error()
      const plan = await res.json()
      const ex = await apiFetch(`plans/${plan.id}/expand`, { method: 'POST' })
      if (!ex.ok) throw new Error()
      const result = await ex.json()
      setGen((g) => ({ ...g, [r.id]: { status: 'ok', days: result.days } }))
    } catch {
      setGen((g) => ({ ...g, [r.id]: { status: 'error' } }))
    }
  }
```

Tabela: header ganha `<th className="font-normal">Plano</th>` (depois de Local) e cada linha ganha a célula:
```tsx
                    <td className="py-1.5">
                      {isFutureRace(r, todayIso()) && (
                        gen[r.id]?.status === 'ok' ? (
                          <span className="text-xs text-emerald-600 dark:text-emerald-400">
                            Plano gerado: {gen[r.id].days} treinos · <a href="/plano" className="underline">Ver plano</a>
                          </span>
                        ) : (
                          <span className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => generatePlan(r)}
                              disabled={gen[r.id]?.status === 'busy'}
                              className="rounded-lg border border-blue-300 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-50 dark:border-blue-500/40 dark:text-blue-300 dark:hover:bg-blue-500/10"
                            >
                              {gen[r.id]?.status === 'busy' ? 'Gerando…' : 'Gerar plano'}
                            </button>
                            {gen[r.id]?.status === 'error' && (
                              <span className="text-xs text-red-600">Não foi possível gerar o plano.</span>
                            )}
                          </span>
                        )
                      )}
                    </td>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run components/provas`
Expected: PASS (7 testes)

- [ ] **Step 5: Commit**

```bash
git add web/components/provas
git commit -m "feat(web): botão Gerar plano na página Provas (generate + expand)"
```

---

### Task 5: Verificação completa + PR

- [ ] **Step 1: Suíte web + typecheck no host**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: tudo verde.

- [ ] **Step 2: Push + suíte backend na VM (via usuário)** — comando das Global Constraints; esperado 612+ testes verdes (2 novos).

- [ ] **Step 3: PR**

```bash
gh pr create --title "feat(plans): botão Gerar plano na UI + horizonte das bandeiras" --body "..."
```

Corpo: problema (endpoint sem UI; duplicação ao regenerar; poluição de bandeiras), decisões da spec, verificação. Deploy pós-merge: `up -d --build api web` (sem migração).
