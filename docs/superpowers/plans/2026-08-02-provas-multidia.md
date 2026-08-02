# Provas de Múltiplos Dias (Stage Races XCM) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provas podem ocupar 2+ dias consecutivos (`end_date`); calendário marca todos os dias, e o plano não prescreve treino dentro do período de nenhuma prova.

**Architecture:** Coluna nova `races.end_date` (nullable; NULL = 1 dia). Convenção de leitura em todos os consumidores: `ultimo_dia = end_date ?? race_date`. Formulário envia `end_date` calculado a partir de um campo "Dias".

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (helpers de `app/db/migration_utils.py`), Pydantic v2, Next.js 15 + SWR, vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-02-provas-multidia-design.md`

## Global Constraints

- **Backend NÃO roda no host** (não há Python). A suíte backend roda na VM da Contabo (imagem `aath-test`, `/opt/aath-test`) — o executor escreve código e testes, e a rodada da suíte backend acontece no fim, via comando do usuário (`!`). Testes web e typecheck rodam no host: `cd web && npx vitest run` · `npx tsc --noEmit`.
- Migrações novas DEVEM usar os helpers de `app/db/migration_utils.py` (o teste estático `test_migrations_idempotentes.py` falha com DDL cru).
- Máximo do período de prova: **14 dias** (`end_date - race_date <= 13`).
- Branch de trabalho: `feat/provas-multidia` (já existe, contém a spec).
- Textos de UI em português.
- **Fora de escopo** (spec): etapas com métricas próprias, resultado por dia, dias não consecutivos, contexto do LLM (a IA hoje não recebe provas individuais — só stats agregadas de taper; nada a mudar).

---

### Task 1: Modelo + migração `end_date`

**Files:**
- Modify: `backend/app/models/race.py` (classe `Race`, após linha 19)
- Create: `backend/alembic/versions/0013_race_end_date.py`
- Test: `backend/app/tests/test_api/test_race_multiday.py` (novo)

**Interfaces:**
- Produces: coluna `Race.end_date: Mapped[date | None]` — Tasks 2-4 dependem dela.

- [ ] **Step 1: Write the failing test**

```python
"""Provas de múltiplos dias — modelo e schemas (spec 2026-08-02)."""
from __future__ import annotations

from app.models.race import Race


def test_race_tem_end_date_nullable():
    col = Race.__table__.columns["end_date"]
    assert col.nullable is True
```

- [ ] **Step 2: Run test to verify it fails**

Não roda no host (sem Python). Verificação estática: `grep -n "end_date" backend/app/models/race.py` não retorna nada ⇒ o teste falharia com `KeyError: 'end_date'`.

- [ ] **Step 3: Write minimal implementation**

Em `backend/app/models/race.py`, dentro de `Race`, após `race_date`:

```python
    # Último dia da prova para stage races (XCM etc.). NULL = prova de 1 dia.
    # Convenção de leitura: ultimo_dia = end_date ?? race_date.
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
```

Criar `backend/alembic/versions/0013_race_end_date.py`:

```python
"""Provas de múltiplos dias: races.end_date (NULL = prova de 1 dia).

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-02
"""
from __future__ import annotations

import sqlalchemy as sa

from app.db.migration_utils import add_column_if_missing, drop_column_if_exists

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column_if_missing("races", sa.Column("end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    drop_column_if_exists("races", "end_date")
```

- [ ] **Step 4: Run test to verify it passes**

Verificação estática no host: `grep -n "end_date" backend/app/models/race.py` mostra a coluna. A rodada real da suíte acontece na VM ao final (ver Task 8).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/race.py backend/alembic/versions/0013_race_end_date.py backend/app/tests/test_api/test_race_multiday.py
git commit -m "feat(races): coluna end_date para provas de múltiplos dias"
```

---

### Task 2: Schemas com validação de período

**Files:**
- Modify: `backend/app/schemas/race.py:10-26` (`RaceCreate`, `RaceRead`)
- Modify: `backend/app/schemas/calendar.py:12-16` (`RaceMarker`)
- Test: `backend/app/tests/test_api/test_race_multiday.py` (append)

**Interfaces:**
- Consumes: `Race.end_date` (Task 1).
- Produces: `RaceCreate.end_date: date | None` (validado); `RaceMarker.end_date: date | None` — Task 3 preenche, web (Task 5) consome via JSON.

- [ ] **Step 1: Write the failing tests** (append em `test_race_multiday.py`)

```python
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.calendar import RaceMarker
from app.schemas.race import RaceCreate


def _base(**kw):
    return {"name": "Brasil Ride", "race_date": date(2026, 9, 12), **kw}


def test_race_create_sem_end_date_ok():
    r = RaceCreate(**_base())
    assert r.end_date is None


def test_race_create_periodo_valido():
    r = RaceCreate(**_base(end_date=date(2026, 9, 14)))
    assert r.end_date == date(2026, 9, 14)


def test_end_date_antes_do_inicio_rejeitado():
    with pytest.raises(ValidationError):
        RaceCreate(**_base(end_date=date(2026, 9, 11)))


def test_periodo_acima_de_14_dias_rejeitado():
    with pytest.raises(ValidationError):
        RaceCreate(**_base(end_date=date(2026, 9, 26)))  # 15 dias


def test_race_marker_aceita_end_date():
    m = RaceMarker(id="00000000-0000-0000-0000-000000000001", name="X",
                   race_date=date(2026, 9, 12), end_date=date(2026, 9, 14), days_until=3)
    assert m.end_date == date(2026, 9, 14)
```

- [ ] **Step 2: Verify it fails**

Estático: `RaceCreate` não tem `end_date` (TypeError/atributo ignorado ⇒ asserts falham); `RaceMarker` não aceita `end_date`.

- [ ] **Step 3: Write minimal implementation**

`backend/app/schemas/race.py` — em `RaceCreate`, após `race_date`, e o validador no fim da classe (import novo: `model_validator` de `pydantic`):

```python
    end_date: date | None = None  # último dia (stage races); None = 1 dia
```

```python
    @model_validator(mode="after")
    def _valida_periodo(self):
        if self.end_date is not None:
            if self.end_date < self.race_date:
                raise ValueError("end_date não pode ser antes de race_date")
            if (self.end_date - self.race_date).days > 13:
                raise ValueError("prova não pode ter mais de 14 dias")
        return self
```

`RaceRead(RaceCreate)` herda o campo — nada a fazer.

`backend/app/schemas/calendar.py` — em `RaceMarker`, após `race_date`:

```python
    end_date: date | None = None
```

- [ ] **Step 4: Verify** — leitura dos arquivos confere com os snippets; suíte na VM ao final.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/race.py backend/app/schemas/calendar.py backend/app/tests/test_api/test_race_multiday.py
git commit -m "feat(races): schemas aceitam e validam end_date (máx. 14 dias)"
```

---

### Task 3: Calendário marca todos os dias da prova

**Files:**
- Modify: `backend/app/api/routes/calendar.py:43-50` (query) e `:71-78` (marcadores)
- Test: `backend/app/tests/test_api/test_calendar.py` (append, usando as fixtures locais `env`/`client` existentes no arquivo)

**Interfaces:**
- Consumes: `Race.end_date` (Task 1), `RaceMarker.end_date` (Task 2).
- Produces: JSON do calendário com marcador em cada dia do período e `days_until` relativo ao dia 1 (negativo durante a prova).

- [ ] **Step 1: Write the failing test** (append em `test_calendar.py`, seguindo o padrão dos testes existentes do arquivo — mesmo estilo de criação de `Race` com `athlete_id`)

```python
async def test_calendar_prova_multidia_marca_todos_os_dias(client, auth_headers, session, athlete_id):
    session.add(Race(athlete_id=athlete_id, created_by=athlete_id, name="Brasil Ride",
                     race_date=date(2030, 9, 12), end_date=date(2030, 9, 14)))
    await session.commit()

    resp = await client.get("/api/v1/calendar", params={"start": "2030-09-11", "end": "2030-09-15"},
                            headers=auth_headers)
    assert resp.status_code == 200
    days = {d["date"]: d for d in resp.json()["days"]}

    # Véspera: marcador de contagem (faltam 1 dia)
    assert days["2030-09-11"]["races"][0]["days_until"] == 1
    # Dias 1-3 da prova: marcador presente, days_until 0 / -1 / -2
    assert days["2030-09-12"]["races"][0]["days_until"] == 0
    assert days["2030-09-13"]["races"][0]["days_until"] == -1
    assert days["2030-09-14"]["races"][0]["days_until"] == -2
    # Dia seguinte ao fim: sem marcador
    assert days["2030-09-15"]["races"] == []
    # end_date exposto para o front desenhar a faixa
    assert days["2030-09-12"]["races"][0]["end_date"] == "2030-09-14"


async def test_calendar_prova_em_andamento_no_inicio_da_janela(client, auth_headers, session, athlete_id):
    """Prova que começou antes da janela mas ainda está acontecendo aparece."""
    session.add(Race(athlete_id=athlete_id, created_by=athlete_id, name="Stage",
                     race_date=date(2030, 9, 10), end_date=date(2030, 9, 13)))
    await session.commit()

    resp = await client.get("/api/v1/calendar", params={"start": "2030-09-12", "end": "2030-09-13"},
                            headers=auth_headers)
    days = {d["date"]: d for d in resp.json()["days"]}
    assert days["2030-09-12"]["races"][0]["name"] == "Stage"
```

- [ ] **Step 2: Verify it fails** — hoje o filtro é `d < rc.race_date` (marcador só ANTES da prova) e a query corta `race_date >= start`; os dois testes falham.

- [ ] **Step 3: Write minimal implementation** em `calendar.py`:

Query (linhas 45-49) — prova ainda relevante se o ÚLTIMO dia ≥ start (import: `from sqlalchemy import func, select`):

```python
    races_stmt = (
        select(Race)
        .where(Race.deleted_at.is_(None), Race.athlete_id == ctx.athlete_id,
               func.coalesce(Race.end_date, Race.race_date) >= start)
    )
```

Marcadores (linhas 71-78) — aparecem até o último dia do período:

```python
        # Marcador em todo dia até o FIM da prova: antes dela é contagem
        # regressiva (days_until > 0); durante, days_until <= 0 ("dia 2 de 3").
        day_races = [rc for rc in races if d <= (rc.end_date or rc.race_date)]
        days.append(CalendarDay(
            date=d,
            planned=[PlannedWorkoutRead.model_validate(p) for p in by_day_planned.get(d, [])],
            completed=[WorkoutCompletedRead.model_validate(c) for c in day_completed],
            races=[RaceMarker(id=rc.id, name=rc.name, race_date=rc.race_date,
                              end_date=rc.end_date,
                              days_until=(rc.race_date - d).days) for rc in day_races],
        ))
```

- [ ] **Step 4: Verify** — leitura confere; suíte na VM ao final.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/calendar.py backend/app/tests/test_api/test_calendar.py
git commit -m "feat(calendar): marcador de prova em todos os dias do período"
```

---

### Task 4: Plano não prescreve treino em dia de prova

**Files:**
- Modify: `backend/app/services/planning/plan_expander.py:68-79` (`allocate_days`) e `:170-180` (`expand_plan_to_daily`)
- Test: `backend/app/tests/test_planning/test_plan_expander.py` (append)

**Interfaces:**
- Consumes: `Race.end_date` (Task 1).
- Produces: `allocate_days(..., blocked_days: frozenset[date] = frozenset())` — dias em `blocked_days` nunca recebem `DailyPlanned`. `expand_plan_to_daily` monta `blocked_days` com TODOS os dias de TODAS as provas ativas do atleta (períodos `race_date..end_date??race_date`).

**Atenção:** bloquear o próprio `race_date` muda o comportamento atual (o plano prescrevia treino no dia da prova-alvo). É intencional — spec: "nenhum treino prescrito em dia que caia dentro do período de uma prova". Se algum teste existente de `test_plan_expander.py` ou `test_plan_expand.py` assertar treino no dia da prova, atualize-o citando a spec 2026-08-02 no comentário.

- [ ] **Step 1: Write the failing test** (append em `test_plan_expander.py`, seguindo os imports/helpers do próprio arquivo — `allocate_days` e `WeekSpec` já são usados lá)

```python
def test_allocate_days_pula_dias_bloqueados():
    """Dias dentro de período de prova não recebem treino (spec 2026-08-02)."""
    today = date(2030, 9, 1)  # segunda
    weeks = [WeekSpec(date(2030, 9, 1), "build", 400.0, False)]
    blocked = frozenset({date(2030, 9, 4), date(2030, 9, 5)})
    out = allocate_days(weeks, ftp=250.0, race_date=date(2030, 9, 30),
                        rest_per_week=1, today=today, blocked_days=blocked)
    planned_dates = {d.planned_date for d in out}
    assert planned_dates.isdisjoint(blocked)
    assert planned_dates  # ainda prescreve nos dias livres
```

- [ ] **Step 2: Verify it fails** — `allocate_days` não aceita `blocked_days` (TypeError).

- [ ] **Step 3: Write minimal implementation**

`allocate_days` (assinatura + filtro, linhas 68-75):

```python
def allocate_days(
    weeks: list[WeekSpec], ftp: float, race_date: date, rest_per_week: int, today: date,
    blocked_days: frozenset[date] = frozenset(),
) -> list[DailyPlanned]:
    rest_per_week = max(0, min(3, rest_per_week))
    out: list[DailyPlanned] = []
    for wk in weeks:
        day_dates = [wk.week_start + timedelta(days=i) for i in range(7)]
        # Dia de prova nunca recebe treino prescrito (spec 2026-08-02).
        day_dates = [d for d in day_dates
                     if today <= d <= race_date and d not in blocked_days]
```

`expand_plan_to_daily` — antes da chamada de `allocate_days` (linha ~178), buscar as provas e montar o bloqueio (import local no mesmo bloco dos demais: `from app.models.race import Race`):

```python
    races = (await session.execute(
        select(Race).where(Race.athlete_id == athlete_id, Race.deleted_at.is_(None))
    )).scalars().all()
    blocked: set[date] = set()
    for rc in races:
        last = rc.end_date or rc.race_date
        dd = rc.race_date
        while dd <= last:
            blocked.add(dd)
            dd += timedelta(days=1)

    days = allocate_days(
        weeks, ftp=ftp, race_date=plan.race_date, rest_per_week=rest, today=today,
        blocked_days=frozenset(blocked),
    )
```

(`timedelta` já é importado no topo do módulo; `select` já é importado no bloco local da função.)

- [ ] **Step 4: Verify** — leitura confere; suíte na VM ao final (atenção ao aviso sobre testes existentes acima).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/planning/plan_expander.py backend/app/tests/test_planning/test_plan_expander.py
git commit -m "feat(plan): dias de prova bloqueiam prescrição de treino"
```

---

### Task 5: Web — tipos e helpers de período

**Files:**
- Modify: `web/lib/types.ts:15` (`RaceMarker`) e `:70` (`Race`)
- Modify: `web/lib/races.ts`
- Test: `web/lib/__tests__/races.test.ts` (append)

**Interfaces:**
- Consumes: JSON novo da API (`end_date` em `Race` e `RaceMarker`).
- Produces: `endDateFromDays(raceDate: string, days: number): string | null` e `racePeriodLabel(race: Pick<Race, 'race_date' | 'end_date'>): string` — Tasks 6-7 usam.

- [ ] **Step 1: Write the failing tests** (append em `races.test.ts`)

```ts
import { endDateFromDays, racePeriodLabel } from '@/lib/races'

describe('endDateFromDays', () => {
  it('1 dia → null (prova de um dia não envia end_date)', () => {
    expect(endDateFromDays('2026-09-12', 1)).toBeNull()
  })
  it('3 dias → dois dias depois', () => {
    expect(endDateFromDays('2026-09-12', 3)).toBe('2026-09-14')
  })
  it('cruza fim de mês', () => {
    expect(endDateFromDays('2026-09-30', 2)).toBe('2026-10-01')
  })
})

describe('racePeriodLabel', () => {
  it('um dia mostra só a data', () => {
    expect(racePeriodLabel({ race_date: '2026-09-12', end_date: null })).toBe('2026-09-12')
  })
  it('multi-dia mostra o período', () => {
    expect(racePeriodLabel({ race_date: '2026-09-12', end_date: '2026-09-14' })).toBe('2026-09-12 – 2026-09-14')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run lib/__tests__/races.test.ts`
Expected: FAIL — `endDateFromDays`/`racePeriodLabel` não exportados.

- [ ] **Step 3: Write minimal implementation**

`web/lib/types.ts`:

```ts
export type RaceMarker = { id: string; name: string; race_date: string; end_date?: string | null; days_until: number }
```

e no type `Race`, junto de `race_date`: `end_date?: string | null`.

`web/lib/races.ts` (append):

```ts
/** Converte "Dias" do formulário em end_date ISO; 1 dia → null (não envia). */
export function endDateFromDays(raceDate: string, days: number): string | null {
  if (!raceDate || days <= 1) return null
  const d = new Date(`${raceDate}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days - 1)
  return d.toISOString().slice(0, 10)
}

/** Rótulo da coluna Data: "2026-09-12" ou "2026-09-12 – 2026-09-14". */
export function racePeriodLabel(race: { race_date: string; end_date?: string | null }): string {
  return race.end_date ? `${race.race_date} – ${race.end_date}` : race.race_date
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run lib/__tests__/races.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/lib/types.ts web/lib/races.ts web/lib/__tests__/races.test.ts
git commit -m "feat(web): helpers de período para provas multi-dia"
```

---

### Task 6: Web — campo "Dias" no formulário e período na tabela

**Files:**
- Modify: `web/components/provas/ProvasView.tsx`
- Test: `web/components/provas/__tests__/ProvasView.test.tsx` (append, seguindo os mocks existentes do arquivo)

**Interfaces:**
- Consumes: `endDateFromDays`, `racePeriodLabel` (Task 5).
- Produces: POST `/races` com `end_date` calculado; coluna Data renderiza o período.

- [ ] **Step 1: Write the failing tests** (append dentro do `describe('ProvasView')` em `ProvasView.test.tsx`. O arquivo moca `globalThis.fetch` direto — os labels envolvem os inputs, então `getByLabelText` funciona. Acrescentar `fireEvent` ao import de `@testing-library/react`.)

```tsx
  it('envia end_date calculado a partir do campo Dias', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    render(<ProvasView />)
    fireEvent.change(screen.getByLabelText(/Nome da prova/), { target: { value: 'Brasil Ride' } })
    fireEvent.change(screen.getByLabelText(/^Data$/), { target: { value: '2026-09-12' } })
    fireEvent.change(screen.getByLabelText(/Dias/), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: /Cadastrar prova/ }))
    await waitFor(() => {
      const post = spy.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(post).toBeTruthy()
      expect(JSON.parse(String(post![1]!.body))).toMatchObject({ end_date: '2026-09-14' })
    })
  })

  it('Dias = 1 não envia end_date', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    render(<ProvasView />)
    fireEvent.change(screen.getByLabelText(/Nome da prova/), { target: { value: 'XCO Local' } })
    fireEvent.change(screen.getByLabelText(/^Data$/), { target: { value: '2026-09-12' } })
    fireEvent.click(screen.getByRole('button', { name: /Cadastrar prova/ }))
    await waitFor(() => {
      const post = spy.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(post).toBeTruthy()
      expect(JSON.parse(String(post![1]!.body))).toMatchObject({ end_date: null })
    })
  })

  it('tabela mostra o período quando end_date existe', async () => {
    const race = {
      id: 'r1', athlete_id: 'a', name: 'Brasil Ride', race_date: '2026-09-12',
      end_date: '2026-09-14', priority: 'A', discipline: 'XCM', location: null,
      distance_km: null, elevation_gain_m: null, notes: null, created_at: '2026-08-02T00:00:00Z',
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([race]), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    render(<ProvasView />)
    await waitFor(() => expect(screen.getByText('2026-09-12 – 2026-09-14')).toBeInTheDocument())
  })
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run components/provas`
Expected: FAIL — não existe campo "Dias" nem período na tabela.

- [ ] **Step 3: Write minimal implementation** em `ProvasView.tsx`:

Estado (junto dos demais, linha ~17): `const [days, setDays] = useState('1')`
`reset()` inclui `setDays('1')`.

No body do `submit()` (após `race_date`):

```ts
        end_date: endDateFromDays(raceDate, Number(days) || 1),
```

Campo no grid principal (após o input de Data):

```tsx
            <label className="text-sm">
              <span className="text-slate-600 dark:text-slate-300">Dias (provas de etapas)</span>
              <input type="number" min={1} max={14} value={days}
                     onChange={(e) => setDays(e.target.value)} className={inputCls} />
            </label>
```

Tabela (linha ~147): `{racePeriodLabel(r)}` no lugar de `{r.race_date}`.

Imports: adicionar `endDateFromDays, racePeriodLabel` ao import de `@/lib/races`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run components/provas`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/components/provas/ProvasView.tsx web/components/provas/__tests__/ProvasView.test.tsx
git commit -m "feat(web): cadastro de provas com múltiplos dias (campo Dias)"
```

---

### Task 7: Web — bandeira da prova durante o período no calendário

**Files:**
- Modify: `web/components/calendar/CalendarGrid.tsx:11-14` (`RaceFlag`) e `:40`
- Test: `web/components/calendar/__tests__/CalendarGrid.test.tsx` (append)

**Interfaces:**
- Consumes: `RaceMarker.days_until` agora pode ser ≤ 0 (durante a prova) e `end_date` (Task 3/5).
- Produces: durante a prova o flag mostra "DIA X DA PROVA" em vez de contagem negativa.

- [ ] **Step 1: Write the failing test** (append dentro do `describe('CalendarGrid')` em `CalendarGrid.test.tsx` — o arquivo já monta `days`/`weeks` tipados no topo)

```tsx
  it('durante a prova mostra "DIA X DA PROVA" em vez de contagem negativa', () => {
    const raceDays: CalendarDay[] = [
      {
        date: '2030-09-13', planned: [], completed: [],
        races: [{ id: 'r1', name: 'Brasil Ride', race_date: '2030-09-12', end_date: '2030-09-14', days_until: -1 }],
      },
    ]
    render(<CalendarGrid days={raceDays} weeks={[]} onOpenWorkout={() => {}} />)
    expect(screen.getByText(/DIA 2 DA PROVA/)).toBeInTheDocument()
    expect(screen.queryByText(/-1 DAYS/)).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run components/calendar`
Expected: FAIL — hoje renderiza `-1 DAYS UNTIL EVENT`.

- [ ] **Step 3: Write minimal implementation** em `CalendarGrid.tsx` (linhas 11-14):

```tsx
function RaceFlag({ name, daysUntil }: { name: string; daysUntil: number }) {
  const label = daysUntil > 0
    ? `${daysUntil} DAYS UNTIL EVENT`
    : `DIA ${1 - daysUntil} DA PROVA`
```

(mantendo o restante do componente como está; a linha 40 não muda — `days_until` já é repassado.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run components/calendar`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/components/calendar/CalendarGrid.tsx web/components/calendar/__tests__/CalendarGrid.test.tsx
git commit -m "feat(web): calendário mostra dia da prova durante o período"
```

---

### Task 8: Verificação completa + PR

**Files:** nenhum novo.

- [ ] **Step 1: Suíte web completa + typecheck no host**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: tudo verde.

- [ ] **Step 2: Suíte backend na VM (via usuário)**

Pedir ao usuário para rodar (o Bash do agente não alcança a chave SSH):

```
! ssh -i ~/.ssh/id_ed25519_aath_vps -o IdentitiesOnly=yes root@62.171.128.103 "cd /opt/aath-test && git fetch origin feat/provas-multidia && git checkout feat/provas-multidia && git pull && docker run --rm -v /opt/aath-test/backend:/app aath-test pytest -q"
```

Expected: suíte verde (600+ testes, incluindo os novos). Se `test_plan_expander`/`test_plan_expand` pré-existentes falharem por assertarem treino no dia da prova, atualizar conforme a nota da Task 4 e rodar de novo.

- [ ] **Step 3: Migração real na VM** (Postgres descartável, padrão do PR #23 — via usuário; alternativa: aceitar a verificação da suíte + guarda estática, e validar a 0013 no deploy)

- [ ] **Step 4: Push + PR**

```bash
git push -u origin feat/provas-multidia
gh pr create --title "feat(races): provas de múltiplos dias (stage races XCM)" --body "..."
```

Corpo do PR: problema (XCM de 2-3 dias), decisões da spec (período+totais; taper no dia 1; prova bloqueia dias; máx. 14), o aviso da mudança de comportamento da Task 4, e a verificação executada.

**Deploy (pós-merge, via usuário):** `git pull` + `up -d --build api worker beat web` + `alembic upgrade head` no container da api (a 0013 é aditiva e reversível).
