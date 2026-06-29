# SPA Calendário + Detalhe do Treino — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir uma SPA React/Vite/TS (em `web/`) que consome a FastAPI atual e entrega, no nível TrainingPeaks, um calendário semanal rico e a tela de detalhe do treino, mais 2 endpoints read-only de apoio.

**Architecture:** Backend ganha 2 endpoints aditivos (`GET /calendar` agregador e `GET /workouts/{id}/streams` downsampled), sem alterar contratos existentes. O frontend é uma SPA isolada em `web/` que roda ao lado do Streamlit, com lógica pura testável (`web/src/lib`), hooks TanStack Query (`web/src/api`) e componentes por feature (`web/src/features/{calendar,workout}`).

**Tech Stack:** Backend: FastAPI + SQLAlchemy async + pytest (SQLite em memória nos testes). Frontend: Vite + React 18 + TypeScript + Tailwind + shadcn/ui + TanStack Query + React Router + uPlot; testes Vitest + React Testing Library.

## Global Constraints

- Nenhum endpoint ou schema existente muda de contrato — somente **adições**.
- Todo acesso a dados de atleta passa pelos repositórios tenant-scoped (`TenantRepository`); nunca consultar models direto sem o filtro de tenant.
- Targets de potência no `structure` são **frações do FTP** (0.88 == 88% FTP); watts = `fraction * ftp_watts`.
- Backend tests rodam via: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -q"`.
- Frontend roda em Node 20+. Comandos de teste do front: `cd web && npm test` (Vitest, modo run).
- A SPA **não substitui** o Streamlit neste ciclo; sobe em serviço/porta próprios.
- Datas no backend são `datetime.date`; o frontend troca ISO strings (`YYYY-MM-DD`).
- TDD: teste falhando antes da implementação; commits frequentes por tarefa.

---

## Phase 1 — Backend

### Task 1: Repositório de treinos planejados por intervalo

**Files:**
- Modify: `backend/app/repositories/plan_repo.py`
- Test: `backend/app/tests/test_repositories/test_planned_workout_repo.py`

**Interfaces:**
- Consumes: `WorkoutPlanned` model; `TenantRepository._base_select`.
- Produces: `PlannedWorkoutRepository(session, ctx).list_between(start: date, end: date, athlete_id=None) -> list[WorkoutPlanned]` (ordenado por `planned_date`).

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_repositories/test_planned_workout_repo.py
import uuid
from datetime import date

import pytest

from app.core.tenant import TenantContext
from app.models.enums import Role, WorkoutType
from app.models.workout import WorkoutPlanned
from app.repositories.plan_repo import PlannedWorkoutRepository


def _ctx(aid):
    return TenantContext(athlete_id=aid, tenant_id="t", role=Role.ATHLETE)


@pytest.mark.asyncio
async def test_list_between_filters_by_date_and_tenant(session):
    a, b = uuid.uuid4(), uuid.uuid4()
    for aid, d in [(a, date(2026, 5, 11)), (a, date(2026, 5, 13)), (a, date(2026, 6, 1)), (b, date(2026, 5, 12))]:
        session.add(WorkoutPlanned(athlete_id=aid, planned_date=d, name="T",
                                   workout_type=WorkoutType.ENDURANCE))
    await session.flush()

    repo = PlannedWorkoutRepository(session, _ctx(a))
    rows = await repo.list_between(date(2026, 5, 11), date(2026, 5, 31))

    assert [r.planned_date for r in rows] == [date(2026, 5, 11), date(2026, 5, 13)]  # ordenado, sem 6/1, sem o de B
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_repositories/test_planned_workout_repo.py -q"`
Expected: FAIL — `ImportError: cannot import name 'PlannedWorkoutRepository'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to backend/app/repositories/plan_repo.py
from app.models.workout import WorkoutPlanned


class PlannedWorkoutRepository(TenantRepository[WorkoutPlanned]):
    model = WorkoutPlanned

    async def list_between(
        self, start: date, end: date, athlete_id: uuid.UUID | None = None
    ) -> list[WorkoutPlanned]:
        stmt = (
            self._base_select(athlete_id)
            .where(WorkoutPlanned.planned_date >= start)
            .where(WorkoutPlanned.planned_date <= end)
            .order_by(WorkoutPlanned.planned_date)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
```

- [ ] **Step 4: Run test to verify it passes**

Run: same command as Step 2.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/plan_repo.py backend/app/tests/test_repositories/test_planned_workout_repo.py
git commit -m "feat(api): PlannedWorkoutRepository.list_between (planejados por intervalo)"
```

---

### Task 2: Endpoint agregador `GET /calendar`

**Files:**
- Create: `backend/app/schemas/calendar.py`
- Create: `backend/app/api/routes/calendar.py`
- Modify: `backend/app/api/routes/__init__.py` (registrar o router)
- Test: `backend/app/tests/test_api/test_calendar.py`

**Interfaces:**
- Consumes: `WorkoutRepository.list_between`, `PlannedWorkoutRepository.list_between` (Task 1), `RaceRepository`/select de `Race`, `LoadMetric` série; `get_tenant` dep.
- Produces: `GET /api/v1/calendar?start=&end=` → `CalendarResponse`:
  - `CalendarDay { date: date, planned: list[PlannedWorkoutRead], completed: list[WorkoutCompletedRead], races: list[RaceMarker] }`
  - `RaceMarker { id: UUID, name: str, race_date: date, days_until: int }`
  - `WeekSummary { week_start: date, ctl: float|None, atl: float|None, tsb: float|None, total_duration_s: int, total_tss: float, total_distance_m: float, total_elevation_m: float, total_kj: float }`
  - `CalendarResponse { days: list[CalendarDay], weeks: list[WeekSummary] }`

- [ ] **Step 1: Write the schemas**

```python
# backend/app/schemas/calendar.py
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel

from app.schemas.planning import PlannedWorkoutRead
from app.schemas.workout import WorkoutCompletedRead


class RaceMarker(BaseModel):
    id: uuid.UUID
    name: str
    race_date: date
    days_until: int


class CalendarDay(BaseModel):
    date: date
    planned: list[PlannedWorkoutRead] = []
    completed: list[WorkoutCompletedRead] = []
    races: list[RaceMarker] = []


class WeekSummary(BaseModel):
    week_start: date
    ctl: float | None = None
    atl: float | None = None
    tsb: float | None = None
    total_duration_s: int = 0
    total_tss: float = 0.0
    total_distance_m: float = 0.0
    total_elevation_m: float = 0.0
    total_kj: float = 0.0


class CalendarResponse(BaseModel):
    days: list[CalendarDay] = []
    weeks: list[WeekSummary] = []
```

- [ ] **Step 2: Write the failing test**

```python
# backend/app/tests/test_api/test_calendar.py
import uuid
from datetime import date, datetime, timezone

import pytest

from app.models.enums import WorkoutType
from app.models.race import Race
from app.models.workout import WorkoutCompleted, WorkoutPlanned


async def _seed(session, aid):
    session.add(WorkoutPlanned(athlete_id=aid, planned_date=date(2026, 5, 12),
                               name="Z2", workout_type=WorkoutType.ENDURANCE,
                               planned_tss=80, planned_duration_s=3600))
    session.add(WorkoutCompleted(athlete_id=aid, started_at=datetime(2026, 5, 12, 6, tzinfo=timezone.utc),
                                 workout_date=date(2026, 5, 12), name="Z2 feito",
                                 workout_type=WorkoutType.ENDURANCE, duration_s=3600,
                                 distance_m=30000, elevation_gain_m=200, tss=82, kj=900))
    session.add(Race(athlete_id=aid, name="WOS Canastra", race_date=date(2026, 5, 20)))
    await session.flush()


@pytest.mark.asyncio
async def test_calendar_aggregates_day_and_week(client, auth_headers, session, athlete_id):
    await _seed(session, athlete_id)
    r = await client.get("/api/v1/calendar?start=2026-05-11&end=2026-05-17", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    day = next(d for d in body["days"] if d["date"] == "2026-05-12")
    assert day["planned"][0]["name"] == "Z2"
    assert day["completed"][0]["tss"] == 82
    assert day["races"][0]["name"] == "WOS Canastra"
    assert day["races"][0]["days_until"] == 8
    wk = next(w for w in body["weeks"] if w["week_start"] == "2026-05-11")
    assert wk["total_tss"] == 82
    assert wk["total_distance_m"] == 30000


@pytest.mark.asyncio
async def test_calendar_is_tenant_isolated(client, auth_headers, session, athlete_id):
    other = uuid.uuid4()
    session.add(WorkoutCompleted(athlete_id=other, started_at=datetime(2026, 5, 12, 6, tzinfo=timezone.utc),
                                 workout_date=date(2026, 5, 12), name="de outro",
                                 workout_type=WorkoutType.ENDURANCE, tss=50))
    await session.flush()
    r = await client.get("/api/v1/calendar?start=2026-05-11&end=2026-05-17", headers=auth_headers)
    assert all(not d["completed"] for d in r.json()["days"])  # não vê treino de outro tenant
```

> NOTE: `client`, `auth_headers`, `athlete_id` são fixtures existentes em `backend/app/tests/conftest.py` (usadas pelos testes de `test_api`). Se algum não existir com esse nome, espelhe o padrão já usado em `test_api/test_onboarding.py`.

- [ ] **Step 3: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_calendar.py -q"`
Expected: FAIL — 404 (rota não registrada).

- [ ] **Step 4: Write the route**

```python
# backend/app/api/routes/calendar.py
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.models.metrics import LoadMetric
from app.models.race import Race
from app.repositories.plan_repo import PlannedWorkoutRepository
from app.repositories.workout_repo import WorkoutRepository
from app.schemas.calendar import (
    CalendarDay,
    CalendarResponse,
    RaceMarker,
    WeekSummary,
)
from app.schemas.planning import PlannedWorkoutRead
from app.schemas.workout import WorkoutCompletedRead

router = APIRouter(prefix="/calendar", tags=["calendar"])


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


@router.get("", response_model=CalendarResponse)
async def get_calendar(
    start: date = Query(...),
    end: date = Query(...),
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> CalendarResponse:
    completed = await WorkoutRepository(db, ctx).list_between(start, end)
    planned = await PlannedWorkoutRepository(db, ctx).list_between(start, end)

    races_stmt = (
        select(Race)
        .where(Race.deleted_at.is_(None), Race.athlete_id == ctx.athlete_id,
               Race.race_date >= start, Race.race_date <= end)
    )
    races = list((await db.execute(races_stmt)).scalars().all())

    load_stmt = (
        select(LoadMetric)
        .where(LoadMetric.deleted_at.is_(None), LoadMetric.athlete_id == ctx.athlete_id,
               LoadMetric.metric_date >= start, LoadMetric.metric_date <= end)
    )
    loads = {lm.metric_date: lm for lm in (await db.execute(load_stmt)).scalars().all()}

    by_day_planned: dict[date, list] = defaultdict(list)
    for p in planned:
        by_day_planned[p.planned_date].append(p)
    by_day_completed: dict[date, list] = defaultdict(list)
    for c in completed:
        by_day_completed[c.workout_date].append(c)
    by_day_races: dict[date, list] = defaultdict(list)
    for rc in races:
        by_day_races[rc.race_date].append(rc)

    days: list[CalendarDay] = []
    week_acc: dict[date, dict] = {}
    d = start
    while d <= end:
        day_completed = by_day_completed.get(d, [])
        days.append(CalendarDay(
            date=d,
            planned=[PlannedWorkoutRead.model_validate(p) for p in by_day_planned.get(d, [])],
            completed=[WorkoutCompletedRead.model_validate(c) for c in day_completed],
            races=[RaceMarker(id=rc.id, name=rc.name, race_date=rc.race_date,
                              days_until=(rc.race_date - d).days) for rc in by_day_races.get(d, [])],
        ))
        wk = week_acc.setdefault(_monday(d), {
            "total_duration_s": 0, "total_tss": 0.0, "total_distance_m": 0.0,
            "total_elevation_m": 0.0, "total_kj": 0.0, "ctl": None, "atl": None, "tsb": None,
        })
        for c in day_completed:
            wk["total_duration_s"] += c.duration_s or 0
            wk["total_tss"] += c.tss or 0.0
            wk["total_distance_m"] += c.distance_m or 0.0
            wk["total_elevation_m"] += c.elevation_gain_m or 0.0
            wk["total_kj"] += c.kj or 0.0
        lm = loads.get(d)
        if lm is not None:  # último valor PMC da semana representa Fitness/Fatigue/Form
            wk["ctl"], wk["atl"], wk["tsb"] = lm.ctl, lm.atl, lm.tsb
        d += timedelta(days=1)

    weeks = [WeekSummary(week_start=ws, **vals) for ws, vals in sorted(week_acc.items())]
    return CalendarResponse(days=days, weeks=weeks)
```

- [ ] **Step 5: Register the router**

In `backend/app/api/routes/__init__.py`, import `calendar` and include its router exactly like the sibling routers already do (find the block that does `from app.api.routes import ... workouts` and `api_router.include_router(workouts.router)`; add `calendar` in both places).

```python
# add to the imports tuple/line
from app.api.routes import calendar
# add next to the other include_router calls
api_router.include_router(calendar.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_calendar.py -q"`
Expected: PASS (2 tests).

> If `LoadMetric` / `Race` import paths differ, confirm with `grep -rn "class LoadMetric" backend/app/models` and `class Race`. Adjust imports to the real module.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/calendar.py backend/app/api/routes/calendar.py backend/app/api/routes/__init__.py backend/app/tests/test_api/test_calendar.py
git commit -m "feat(api): GET /calendar agrega planejado+executado+provas+resumo semanal"
```

---

### Task 3: Endpoint `GET /workouts/{id}/streams` com downsample

**Files:**
- Create: `backend/app/services/metrics/downsample.py`
- Create: `backend/app/schemas/streams.py`
- Modify: `backend/app/api/routes/workouts.py`
- Test (pure): `backend/app/tests/test_metrics/test_downsample.py`
- Test (api): `backend/app/tests/test_api/test_workout_streams.py`

**Interfaces:**
- Produces:
  - `downsample(values: list[float | None] | None, n: int) -> list[float | None]` — média por bucket; `None`/vazio → `[]`; se `len <= n` retorna cópia; buckets sem valores numéricos → `None`.
  - `GET /api/v1/workouts/{id}/streams?max_points=<int>` → `WorkoutStreamsRead { workout_id, n_points, time_s, power, heart_rate, cadence, altitude }` (cada série já downsampled a `n_points <= max_points`).

- [ ] **Step 1: Write the failing pure test**

```python
# backend/app/tests/test_metrics/test_downsample.py
from app.services.metrics.downsample import downsample


def test_downsample_none_and_empty():
    assert downsample(None, 10) == []
    assert downsample([], 10) == []


def test_downsample_keeps_short_series():
    assert downsample([1.0, 2.0, 3.0], 10) == [1.0, 2.0, 3.0]


def test_downsample_buckets_average():
    # 6 pontos para 3 buckets → médias [1.5, 3.5, 5.5]
    assert downsample([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], 3) == [1.5, 3.5, 5.5]


def test_downsample_bucket_all_none_is_none():
    out = downsample([None, None, 4.0, 6.0], 2)
    assert out == [None, 5.0]
```

- [ ] **Step 2: Run pure test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_metrics/test_downsample.py -q"`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement downsample**

```python
# backend/app/services/metrics/downsample.py
from __future__ import annotations

import math


def downsample(values: list[float | None] | None, n: int) -> list[float | None]:
    """Reduz a série a no máximo ``n`` pontos pela média de cada bucket.

    None/vazio → []. Série menor/igual a n → cópia. Bucket sem números → None."""
    if not values:
        return []
    if len(values) <= n or n <= 0:
        return list(values)
    size = len(values) / n
    out: list[float | None] = []
    for i in range(n):
        lo = math.floor(i * size)
        hi = math.floor((i + 1) * size) if i < n - 1 else len(values)
        nums = [v for v in values[lo:hi] if v is not None]
        out.append(round(sum(nums) / len(nums), 2) if nums else None)
    return out
```

- [ ] **Step 4: Run pure test to verify it passes**

Run: same as Step 2. Expected: PASS (4 tests).

- [ ] **Step 5: Write the streams schema**

```python
# backend/app/schemas/streams.py
from __future__ import annotations

import uuid

from pydantic import BaseModel


class WorkoutStreamsRead(BaseModel):
    workout_id: uuid.UUID
    n_points: int
    time_s: list[float | None] = []
    power: list[float | None] = []
    heart_rate: list[float | None] = []
    cadence: list[float | None] = []
    altitude: list[float | None] = []
```

- [ ] **Step 6: Write the failing api test**

```python
# backend/app/tests/test_api/test_workout_streams.py
from datetime import datetime, timezone

import pytest

from app.models.enums import WorkoutType
from app.models.workout import WorkoutCompleted, WorkoutStream


async def _seed_with_streams(session, aid):
    w = WorkoutCompleted(athlete_id=aid, started_at=datetime(2026, 5, 12, 6, tzinfo=timezone.utc),
                         workout_date=datetime(2026, 5, 12).date(), name="Z2",
                         workout_type=WorkoutType.ENDURANCE, duration_s=10)
    session.add(w)
    await session.flush()
    session.add(WorkoutStream(athlete_id=aid, workout_id=w.id, sample_rate_hz=1.0,
                              time_s=list(range(10)), power=[float(i) for i in range(10)],
                              heart_rate=None, cadence=None, altitude=None))
    await session.flush()
    return w


@pytest.mark.asyncio
async def test_streams_downsampled(client, auth_headers, session, athlete_id):
    w = await _seed_with_streams(session, athlete_id)
    r = await client.get(f"/api/v1/workouts/{w.id}/streams?max_points=5", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["n_points"] == 5
    assert len(body["power"]) == 5
    assert body["power"][0] == 0.5  # média do bucket [0,1]


@pytest.mark.asyncio
async def test_streams_404_for_unknown(client, auth_headers):
    import uuid
    r = await client.get(f"/api/v1/workouts/{uuid.uuid4()}/streams", headers=auth_headers)
    assert r.status_code == 404
```

- [ ] **Step 7: Run api test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_workout_streams.py -q"`
Expected: FAIL — 404 on the valid id too (route missing).

- [ ] **Step 8: Add the route to `workouts.py`**

```python
# add imports at top of backend/app/api/routes/workouts.py
from sqlalchemy import select
from app.models.workout import WorkoutStream
from app.schemas.streams import WorkoutStreamsRead
from app.services.metrics.downsample import downsample

# add this route (after get_workout)
@router.get("/{workout_id}/streams", response_model=WorkoutStreamsRead)
async def get_workout_streams(
    workout_id: uuid.UUID,
    max_points: int = Query(default=1200, ge=10, le=5000),
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    repo = WorkoutRepository(db, ctx)
    workout = await repo.get(workout_id)  # tenant-scoped; None se não for do atleta
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    stmt = select(WorkoutStream).where(
        WorkoutStream.deleted_at.is_(None),
        WorkoutStream.athlete_id == ctx.athlete_id,
        WorkoutStream.workout_id == workout_id,
    )
    stream = (await db.execute(stmt)).scalars().first()
    if stream is None:
        return WorkoutStreamsRead(workout_id=workout_id, n_points=0)
    time_s = downsample([float(t) for t in (stream.time_s or [])], max_points)
    power = downsample(stream.power, max_points)
    return WorkoutStreamsRead(
        workout_id=workout_id,
        n_points=len(power) or len(time_s),
        time_s=time_s,
        power=power,
        heart_rate=downsample(stream.heart_rate, max_points),
        cadence=downsample(stream.cadence, max_points),
        altitude=downsample(stream.altitude, max_points),
    )
```

> `Query` já está importado em `workouts.py` (usado em `list_workouts`). Não reimportar.

- [ ] **Step 9: Run api test to verify it passes**

Run: same as Step 7. Expected: PASS (2 tests).

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/metrics/downsample.py backend/app/schemas/streams.py backend/app/api/routes/workouts.py backend/app/tests/test_metrics/test_downsample.py backend/app/tests/test_api/test_workout_streams.py
git commit -m "feat(api): GET /workouts/{id}/streams com downsample por bucket"
```

---

## Phase 2 — Frontend foundation

### Task 4: Scaffold `web/` (Vite + React + TS + Tailwind + shadcn) + app shell

**Files:**
- Create: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html`, `web/tailwind.config.ts`, `web/postcss.config.js`, `web/src/main.tsx`, `web/src/index.css`, `web/src/App.tsx`, `web/src/AppShell.tsx`, `web/.env.development`
- Test: `web/src/App.test.tsx`, `web/vitest.config.ts`, `web/src/test/setup.ts`

**Interfaces:**
- Produces: app bootstrap (`main.tsx` monta `<App/>`), `AppShell` (top-nav com logo + título + slot de conteúdo), e ambiente Vitest+RTL pronto.

- [ ] **Step 1: Create the project config files**

`web/package.json`:
```json
{
  "name": "athlete-hub-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.51.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0",
    "uplot": "^1.6.31"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.8",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "jsdom": "^24.1.1",
    "postcss": "^8.4.40",
    "tailwindcss": "^3.4.7",
    "typescript": "^5.5.4",
    "vite": "^5.3.5",
    "vitest": "^2.0.5"
  }
}
```

`web/vite.config.ts`:
```ts
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
})
```

`web/vitest.config.ts`:
```ts
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test/setup.ts'] },
})
```

`web/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020", "useDefineForClassFields": true, "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext", "skipLibCheck": true, "moduleResolution": "bundler",
    "resolveJsonModule": true, "isolatedModules": true, "noEmit": true, "jsx": "react-jsx",
    "strict": true, "noUnusedLocals": true, "noUnusedParameters": true, "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"]
}
```

`web/tailwind.config.ts`:
```ts
import type { Config } from 'tailwindcss'
export default { content: ['./index.html', './src/**/*.{ts,tsx}'], theme: { extend: {} }, plugins: [] } satisfies Config
```

`web/postcss.config.js`:
```js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } }
```

`web/.env.development`:
```
VITE_API_BASE=/api/v1
```

- [ ] **Step 2: Create the source + shell**

`web/index.html`:
```html
<!doctype html>
<html lang="pt-BR">
  <head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>Athlete Hub</title></head>
  <body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>
</html>
```

`web/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

`web/src/main.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { App } from './App'
import './index.css'

const queryClient = new QueryClient()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
```

`web/src/AppShell.tsx`:
```tsx
import type { ReactNode } from 'react'

export function AppShell({ user, children }: { user?: string; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="flex items-center justify-between bg-slate-900 px-4 py-2 text-white">
        <span className="font-bold tracking-tight">ATHLETE HUB</span>
        <nav className="flex gap-6 text-sm">
          <span className="font-semibold">Calendário</span>
          <span className="opacity-60">Dashboard</span>
        </nav>
        <span className="text-sm opacity-80">{user ?? ''}</span>
      </header>
      <main className="p-4">{children}</main>
    </div>
  )
}
```

`web/src/App.tsx`:
```tsx
import { AppShell } from './AppShell'

export function App() {
  return (
    <AppShell>
      <h1 className="text-xl font-semibold">Calendário</h1>
    </AppShell>
  )
}
```

`web/src/test/setup.ts`:
```ts
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 3: Write the smoke test**

`web/src/App.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { App } from './App'

describe('App', () => {
  it('renderiza o shell com o título Calendário', () => {
    render(<App />)
    expect(screen.getByText('ATHLETE HUB')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Calendário' })).toBeInTheDocument()
  })
})
```

- [ ] **Step 4: Install and run the smoke test**

Run: `cd web && npm install && npm test`
Expected: 1 test PASS. (If running through Docker Node: `docker run --rm -v "$(pwd -W)/web":/w -w /w node:20-slim sh -c "npm install && npm test"`.)

- [ ] **Step 5: Commit**

```bash
git add web/
git commit -m "feat(web): scaffold SPA (Vite+React+TS+Tailwind) + app shell + smoke test"
```

---

### Task 5: Cliente de API + autenticação

**Files:**
- Create: `web/src/api/client.ts`, `web/src/auth/storage.ts`, `web/src/auth/AuthContext.tsx`, `web/src/auth/LoginPage.tsx`
- Test: `web/src/api/client.test.ts`, `web/src/auth/storage.test.ts`

**Interfaces:**
- Consumes: `VITE_API_BASE`.
- Produces:
  - `apiFetch<T>(path: string, opts?: { method?, body?, token?: string | null }): Promise<T>` — prefixa `VITE_API_BASE`, injeta `Authorization: Bearer`, faz `throw new ApiError(status)` em !ok.
  - `tokenStorage.get()/set(t)/clear()` (localStorage, chave `ah_token`).
  - `login(email, password): Promise<string>` (POST `/auth/login` form-urlencoded → access_token).
  - `AuthProvider` + `useAuth()` → `{ token, user, signIn, signOut }`.

- [ ] **Step 1: Write failing tests**

`web/src/auth/storage.test.ts`:
```ts
import { beforeEach, describe, expect, it } from 'vitest'
import { tokenStorage } from './storage'

describe('tokenStorage', () => {
  beforeEach(() => localStorage.clear())
  it('set/get/clear', () => {
    expect(tokenStorage.get()).toBeNull()
    tokenStorage.set('abc')
    expect(tokenStorage.get()).toBe('abc')
    tokenStorage.clear()
    expect(tokenStorage.get()).toBeNull()
  })
})
```

`web/src/api/client.test.ts`:
```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch } from './client'

afterEach(() => vi.restoreAllMocks())

describe('apiFetch', () => {
  it('injeta Bearer e parseia json', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: 1 }), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    const out = await apiFetch<{ ok: number }>('/ping', { token: 't1' })
    expect(out.ok).toBe(1)
    const [, init] = spy.mock.calls[0]
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer t1')
  })

  it('lança ApiError em status !ok', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('nope', { status: 401 }))
    await expect(apiFetch('/x')).rejects.toBeInstanceOf(ApiError)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npm test`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement client + storage**

`web/src/auth/storage.ts`:
```ts
const KEY = 'ah_token'
export const tokenStorage = {
  get: (): string | null => localStorage.getItem(KEY),
  set: (t: string) => localStorage.setItem(KEY, t),
  clear: () => localStorage.removeItem(KEY),
}
```

`web/src/api/client.ts`:
```ts
const BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'

export class ApiError extends Error {
  constructor(public status: number, message?: string) {
    super(message ?? `API error ${status}`)
  }
}

export async function apiFetch<T>(
  path: string,
  opts: { method?: string; body?: unknown; token?: string | null; form?: URLSearchParams } = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`
  let body: BodyInit | undefined
  if (opts.form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    body = opts.form
  } else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  const res = await fetch(`${BASE}${path}`, { method: opts.method ?? 'GET', headers, body })
  if (!res.ok) throw new ApiError(res.status)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export async function login(email: string, password: string): Promise<string> {
  const form = new URLSearchParams({ username: email, password })
  const out = await apiFetch<{ access_token: string }>('/auth/login', { method: 'POST', form })
  return out.access_token
}
```

- [ ] **Step 4: Implement AuthContext + LoginPage**

`web/src/auth/AuthContext.tsx`:
```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { apiFetch, login as apiLogin } from '../api/client'
import { tokenStorage } from './storage'

type AuthState = { token: string | null; user: string | null; signIn: (e: string, p: string) => Promise<void>; signOut: () => void }
const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => tokenStorage.get())
  const [user, setUser] = useState<string | null>(null)

  useEffect(() => {
    if (!token) { setUser(null); return }
    apiFetch<{ full_name?: string; email: string }>('/auth/me', { token })
      .then((u) => setUser(u.full_name ?? u.email))
      .catch(() => { tokenStorage.clear(); setToken(null) })
  }, [token])

  const signIn = async (email: string, password: string) => {
    const t = await apiLogin(email, password)
    tokenStorage.set(t)
    setToken(t)
  }
  const signOut = () => { tokenStorage.clear(); setToken(null) }

  return <Ctx.Provider value={{ token, user, signIn, signOut }}>{children}</Ctx.Provider>
}

export function useAuth(): AuthState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth fora do AuthProvider')
  return v
}
```

`web/src/auth/LoginPage.tsx`:
```tsx
import { useState } from 'react'
import { useAuth } from './AuthContext'

export function LoginPage() {
  const { signIn } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    try { await signIn(email, password) } catch { setError('Credenciais inválidas') }
  }

  return (
    <form onSubmit={submit} className="mx-auto mt-24 flex w-80 flex-col gap-3 rounded-lg bg-white p-6 shadow">
      <h1 className="text-lg font-semibold">Entrar</h1>
      <input className="rounded border p-2" placeholder="E-mail" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input className="rounded border p-2" type="password" placeholder="Senha" value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && <span className="text-sm text-red-600">{error}</span>}
      <button className="rounded bg-slate-900 p-2 text-white" type="submit">Entrar</button>
    </form>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd web && npm test`
Expected: PASS (storage + client tests).

- [ ] **Step 6: Commit**

```bash
git add web/src/api web/src/auth
git commit -m "feat(web): cliente de API + auth (login JWT, storage, contexto)"
```

---

## Phase 3 — Lógica pura (`web/src/lib`)

### Task 6: `lib/format.ts`

**Files:**
- Create: `web/src/lib/format.ts`
- Test: `web/src/lib/format.test.ts`

**Interfaces:**
- Produces: `formatDuration(s: number | null): string` ("1:54:00"/"0:25:00"/"—"); `formatDistanceKm(m: number | null): string` ("30.0 km"/"—"); `formatTss(n: number | null): string` ("82 TSS"/"—").

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/format.test.ts
import { describe, expect, it } from 'vitest'
import { formatDistanceKm, formatDuration, formatTss } from './format'

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

- [ ] **Step 2: Run to verify it fails** — `cd web && npm test`. Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```ts
// web/src/lib/format.ts
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

- [ ] **Step 4: Run to verify it passes** — `cd web && npm test`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/format.ts web/src/lib/format.test.ts
git commit -m "feat(web): lib/format (duração, distância, tss)"
```

---

### Task 7: `lib/zones.ts`

**Files:**
- Create: `web/src/lib/zones.ts`
- Test: `web/src/lib/zones.test.ts`

**Interfaces:**
- Produces: `powerToZone(watts: number, ftp: number): number` (1..7, Coggan); `pctToZone(pct: number): number` (pct = fração, 0.9 = 90%); `ZONE_COLORS: Record<number, string>`; `zoneColor(zone: number): string`.

Faixas (fração do FTP): Z1 ≤0.55, Z2 0.56–0.75, Z3 0.76–0.90, Z4 0.91–1.05, Z5 1.06–1.20, Z6 1.21–1.50, Z7 >1.50.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/zones.test.ts
import { describe, expect, it } from 'vitest'
import { pctToZone, powerToZone, zoneColor } from './zones'

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
  it('zoneColor é string não vazia', () => {
    expect(zoneColor(4)).toMatch(/^#/)
  })
})
```

- [ ] **Step 2: Run to verify it fails** — `cd web && npm test`. Expected: FAIL.

- [ ] **Step 3: Implement**

```ts
// web/src/lib/zones.ts
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

- [ ] **Step 4: Run to verify it passes** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/zones.ts web/src/lib/zones.test.ts
git commit -m "feat(web): lib/zones (potência→zona Coggan + cores)"
```

---

### Task 8: `lib/structure.ts` (estrutura → segmentos + steps)

**Files:**
- Create: `web/src/lib/structure.ts`
- Test: `web/src/lib/structure.test.ts`

**Interfaces:**
- Consumes: `pctToZone` (Task 7).
- Produces (tipos exportados):
  - `type Segment = { durationS: number; lowW: number | null; highW: number | null; zone: number; intensity: string }`
  - `type WorkoutStructure = { name?: string; elements?: Array<StepEl | RepeatEl>; ftp_watts?: number | null }` onde `StepEl = { intensity: string; duration_s: number; target?: { type: string; low?: number | null; high?: number | null }; note?: string }` e `RepeatEl = { count: number; steps: StepEl[] }`.
  - `structureToSegments(structure: WorkoutStructure | null, ftpFallback?: number): Segment[]` — expande `Repeat` (count×steps), resolve watts = `pct * ftp` (ftp do structure ou fallback), zone do midpoint (low/high) ou da zona aberta = 1.
  - `structureToSteps(structure, ftpFallback?): Array<{ label: string; durationS: number; lowW: number | null; highW: number | null; zone: number }>` — agrupa por bloco rotulado (Warm up/Active/Recovery/Cool Down a partir de `intensity`), 1 linha por step.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/structure.test.ts
import { describe, expect, it } from 'vitest'
import { structureToSegments, structureToSteps } from './structure'

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
    // warmup + (active,rest)x2 + cooldown = 6 segmentos
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

- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.

- [ ] **Step 3: Implement**

```ts
// web/src/lib/structure.ts
import { pctToZone } from './zones'

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

- [ ] **Step 4: Run to verify it passes** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/structure.ts web/src/lib/structure.test.ts
git commit -m "feat(web): lib/structure (estrutura→segmentos+steps, expande repeats)"
```

---

### Task 9: `lib/compliance.ts`

**Files:**
- Create: `web/src/lib/compliance.ts`
- Test: `web/src/lib/compliance.test.ts`

**Interfaces:**
- Produces:
  - `type CardStatus = 'completed' | 'planned' | 'adjusted' | 'rest'`
  - `cardStatus(input: { hasCompleted: boolean; hasAdjustment: boolean; isRest: boolean }): CardStatus` — prioridade: rest > completed > adjusted > planned.
  - `statusColor(status: CardStatus): string` (cor da faixa do card).

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/compliance.test.ts
import { describe, expect, it } from 'vitest'
import { cardStatus, statusColor } from './compliance'

describe('compliance', () => {
  it('prioridade rest > completed > adjusted > planned', () => {
    expect(cardStatus({ hasCompleted: true, hasAdjustment: true, isRest: true })).toBe('rest')
    expect(cardStatus({ hasCompleted: true, hasAdjustment: true, isRest: false })).toBe('completed')
    expect(cardStatus({ hasCompleted: false, hasAdjustment: true, isRest: false })).toBe('adjusted')
    expect(cardStatus({ hasCompleted: false, hasAdjustment: false, isRest: false })).toBe('planned')
  })
  it('cada status tem cor', () => {
    for (const s of ['completed', 'planned', 'adjusted', 'rest'] as const) {
      expect(statusColor(s)).toMatch(/^#/)
    }
  })
})
```

- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.

- [ ] **Step 3: Implement**

```ts
// web/src/lib/compliance.ts
export type CardStatus = 'completed' | 'planned' | 'adjusted' | 'rest'

export function cardStatus(input: { hasCompleted: boolean; hasAdjustment: boolean; isRest: boolean }): CardStatus {
  if (input.isRest) return 'rest'
  if (input.hasCompleted) return 'completed'
  if (input.hasAdjustment) return 'adjusted'
  return 'planned'
}

const COLORS: Record<CardStatus, string> = {
  completed: '#22c55e', // verde — executado
  planned: '#cbd5e1',   // cinza — planejado pendente
  adjusted: '#8b5cf6',  // roxo — ajustado pela IA
  rest: '#e2e8f0',      // descanso
}
export function statusColor(status: CardStatus): string {
  return COLORS[status]
}
```

- [ ] **Step 4: Run to verify it passes** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/compliance.ts web/src/lib/compliance.test.ts
git commit -m "feat(web): lib/compliance (status+cor do card de treino)"
```

---

## Phase 4 — Tipos + hooks de dados

### Task 10: Tipos da API + hooks TanStack Query

**Files:**
- Create: `web/src/api/types.ts`, `web/src/api/hooks.ts`
- Test: `web/src/api/hooks.test.tsx`

**Interfaces:**
- Consumes: `apiFetch`, `useAuth`.
- Produces (tipos espelhando o backend):
  - `PlannedWorkout { id; planned_date; name; workout_type; planned_duration_s: number | null; planned_tss: number | null; description: string | null; structure: WorkoutStructure | null; adjustment: Record<string, unknown> | null }`
  - `CompletedWorkout { id; workout_date; name: string | null; workout_type; duration_s: number | null; distance_m: number | null; tss: number | null; intensity_factor: number | null; avg_power: number | null; normalized_power: number | null; avg_hr: number | null; kj: number | null; elevation_gain_m: number | null; notes: string | null }`
  - `RaceMarker { id; name; race_date; days_until: number }`
  - `CalendarDay { date; planned: PlannedWorkout[]; completed: CompletedWorkout[]; races: RaceMarker[] }`
  - `WeekSummary { week_start; ctl; atl; tsb; total_duration_s; total_tss; total_distance_m; total_elevation_m; total_kj }` (numéricos `number | null` onde aplicável)
  - `WorkoutStreams { workout_id; n_points; time_s; power; heart_rate; cadence; altitude }` (arrays `Array<number | null>`)
  - `useCalendar(start: string, end: string)` → query de `GET /calendar`.
  - `useWorkoutStreams(id: string | null)` → query de `GET /workouts/{id}/streams` (enabled só com id).

- [ ] **Step 1: Write the types**

```ts
// web/src/api/types.ts
import type { WorkoutStructure } from '../lib/structure'

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
// web/src/api/hooks.test.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { useCalendar } from './hooks'

afterEach(() => vi.restoreAllMocks())

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><AuthProvider>{children}</AuthProvider></QueryClientProvider>
}

describe('useCalendar', () => {
  it('busca /calendar e retorna days', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ days: [{ date: '2026-05-12', planned: [], completed: [], races: [] }], weeks: [] }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    const { result } = renderHook(() => useCalendar('2026-05-11', '2026-05-17'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.days[0].date).toBe('2026-05-12')
  })
})
```

- [ ] **Step 3: Run to verify it fails** — Expected: FAIL.

- [ ] **Step 4: Implement hooks**

```ts
// web/src/api/hooks.ts
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { apiFetch } from './client'
import type { CalendarResponse, WorkoutStreams } from './types'

export function useCalendar(start: string, end: string) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['calendar', start, end],
    queryFn: () => apiFetch<CalendarResponse>(`/calendar?start=${start}&end=${end}`, { token }),
    enabled: !!token,
  })
}

export function useWorkoutStreams(id: string | null) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['streams', id],
    queryFn: () => apiFetch<WorkoutStreams>(`/workouts/${id}/streams`, { token }),
    enabled: !!token && !!id,
  })
}
```

- [ ] **Step 5: Run to verify it passes** — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/api/types.ts web/src/api/hooks.ts web/src/api/hooks.test.tsx
git commit -m "feat(web): tipos da API + hooks useCalendar/useWorkoutStreams"
```

---

## Phase 5 — UI do Calendário

### Task 11: `IntensityThumbnail` + `WorkoutCard`

**Files:**
- Create: `web/src/features/calendar/IntensityThumbnail.tsx`, `web/src/features/calendar/WorkoutCard.tsx`
- Test: `web/src/features/calendar/WorkoutCard.test.tsx`

**Interfaces:**
- Consumes: `structureToSegments`, `zoneColor`, `cardStatus`, `statusColor`, `formatDuration`, `formatDistanceKm`, `formatTss`; tipos `PlannedWorkout`/`CompletedWorkout`.
- Produces:
  - `IntensityThumbnail({ segments, height? }: { segments: Segment[]; height?: number })` — SVG de barras proporcionais (largura = duração, altura = %FTP via highW, cor = `zoneColor(zone)`).
  - `WorkoutCard({ planned, completed, onOpen })` — card com faixa de status, ícone, título, duração(+✓), distância, TSS, preview, thumbnail, badge IA. `onOpen(workoutId)` ao clicar.

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/features/calendar/WorkoutCard.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { CompletedWorkout, PlannedWorkout } from '../../api/types'
import { WorkoutCard } from './WorkoutCard'

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
  it('mostra título, tss e duração; chama onOpen com o id', async () => {
    const onOpen = vi.fn()
    render(<WorkoutCard planned={planned} completed={completed} onOpen={onOpen} />)
    expect(screen.getByText('Z2 c/ Z4')).toBeInTheDocument()
    expect(screen.getByText('103 TSS')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button'))
    expect(onOpen).toHaveBeenCalledWith('c1')  // executado tem prioridade de id
  })

  it('exibe badge IA quando há adjustment', () => {
    render(<WorkoutCard planned={{ ...planned, adjustment: { reason: 'x' } }} completed={null} onOpen={() => {}} />)
    expect(screen.getByText('🤖 IA')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.

- [ ] **Step 3: Implement IntensityThumbnail**

```tsx
// web/src/features/calendar/IntensityThumbnail.tsx
import type { Segment } from '../../lib/structure'
import { zoneColor } from '../../lib/zones'

export function IntensityThumbnail({ segments, height = 28 }: { segments: Segment[]; height?: number }) {
  const total = segments.reduce((a, s) => a + s.durationS, 0) || 1
  const maxW = Math.max(1, ...segments.map((s) => s.highW ?? 0))
  let x = 0
  return (
    <svg width="100%" height={height} viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" aria-hidden>
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
// web/src/features/calendar/WorkoutCard.tsx
import type { CompletedWorkout, PlannedWorkout } from '../../api/types'
import { cardStatus, statusColor } from '../../lib/compliance'
import { formatDistanceKm, formatDuration, formatTss } from '../../lib/format'
import { structureToSegments } from '../../lib/structure'
import { IntensityThumbnail } from './IntensityThumbnail'

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
      className="w-full rounded-md border bg-white text-left shadow-sm hover:shadow"
    >
      <div style={{ height: 4, background: statusColor(status) }} className="rounded-t-md" />
      <div className="space-y-1 p-2">
        <div className="flex items-center justify-between">
          <span className="truncate text-sm font-semibold">🚴 {title}</span>
          {planned?.adjustment && <span className="text-xs text-violet-600">🤖 IA</span>}
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <span>{formatDuration(durationS)}{completed ? ' ✓' : ''}</span>
          {completed?.distance_m != null && <span>{formatDistanceKm(completed.distance_m)}</span>}
          <span className="font-medium">{formatTss(tss)}</span>
        </div>
        {planned?.description && <p className="line-clamp-2 text-xs text-slate-500">{planned.description}</p>}
        {segments.length > 0 && <IntensityThumbnail segments={segments} />}
      </div>
    </button>
  )
}
```

- [ ] **Step 5: Run to verify it passes** — `cd web && npm test`. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/calendar/IntensityThumbnail.tsx web/src/features/calendar/WorkoutCard.tsx web/src/features/calendar/WorkoutCard.test.tsx
git commit -m "feat(web): WorkoutCard + thumbnail de intensidade SVG"
```

---

### Task 12: `SummaryColumn`

**Files:**
- Create: `web/src/features/calendar/SummaryColumn.tsx`
- Test: `web/src/features/calendar/SummaryColumn.test.tsx`

**Interfaces:**
- Consumes: `WeekSummary`, `formatDuration`.
- Produces: `SummaryColumn({ week }: { week: WeekSummary })` — bloco com Fitness/Fatigue/Form (CTL/ATL/TSB) + Total Duration/TSS/Distância/El.Gain/Work.

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/features/calendar/SummaryColumn.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { WeekSummary } from '../../api/types'
import { SummaryColumn } from './SummaryColumn'

const week: WeekSummary = {
  week_start: '2026-05-11', ctl: 12, atl: 45, tsb: -12,
  total_duration_s: 49440, total_tss: 767, total_distance_m: 242000, total_elevation_m: 4572, total_kj: 7240,
}

describe('SummaryColumn', () => {
  it('mostra CTL/ATL/TSB e totais', () => {
    render(<SummaryColumn week={week} />)
    expect(screen.getByText('12')).toBeInTheDocument()  // CTL
    expect(screen.getByText('-12')).toBeInTheDocument() // TSB
    expect(screen.getByText(/767/)).toBeInTheDocument() // Total TSS
    expect(screen.getByText(/242/)).toBeInTheDocument() // distância km
  })
})
```

- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.

- [ ] **Step 3: Implement**

```tsx
// web/src/features/calendar/SummaryColumn.tsx
import type { WeekSummary } from '../../api/types'
import { formatDuration } from '../../lib/format'

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}

export function SummaryColumn({ week }: { week: WeekSummary }) {
  const n = (v: number | null) => (v == null ? '—' : String(Math.round(v)))
  return (
    <div className="space-y-2 border-l p-3">
      <div className="grid grid-cols-3 gap-1 text-center">
        {([['Fitness', week.ctl], ['Fatigue', week.atl], ['Form', week.tsb]] as const).map(([k, v]) => (
          <div key={k}>
            <div className="text-[10px] uppercase text-slate-400">{k}</div>
            <div className="text-sm font-semibold">{n(v)}</div>
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

- [ ] **Step 4: Run to verify it passes** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/features/calendar/SummaryColumn.tsx web/src/features/calendar/SummaryColumn.test.tsx
git commit -m "feat(web): SummaryColumn (CTL/ATL/TSB + totais semanais)"
```

---

### Task 13: `CalendarGrid` + página do calendário

**Files:**
- Create: `web/src/features/calendar/CalendarGrid.tsx`, `web/src/features/calendar/weekRange.ts`, `web/src/features/calendar/CalendarPage.tsx`
- Test: `web/src/features/calendar/weekRange.test.ts`, `web/src/features/calendar/CalendarGrid.test.tsx`

**Interfaces:**
- Consumes: `CalendarDay`, `WeekSummary`, `WorkoutCard`, `SummaryColumn`.
- Produces:
  - `mondayOf(iso: string): string`, `weekDays(mondayIso: string): string[]` (7 ISO strings Seg→Dom).
  - `CalendarGrid({ days, weeks, onOpenWorkout }: { days: CalendarDay[]; weeks: WeekSummary[]; onOpenWorkout: (id: string) => void })` — agrupa `days` por semana (Seg–Dom), render 7 colunas + `SummaryColumn` por linha; marcadores de prova; dia de hoje destacado.
  - `CalendarPage()` — usa `useCalendar` para a semana atual, passa `onOpenWorkout` que navega para `/calendar/workout/:id`.

- [ ] **Step 1: Write failing weekRange test**

```ts
// web/src/features/calendar/weekRange.test.ts
import { describe, expect, it } from 'vitest'
import { mondayOf, weekDays } from './weekRange'

describe('weekRange', () => {
  it('mondayOf retorna a segunda da semana', () => {
    expect(mondayOf('2026-05-13')).toBe('2026-05-11') // quarta → segunda
    expect(mondayOf('2026-05-11')).toBe('2026-05-11')
  })
  it('weekDays gera 7 dias Seg→Dom', () => {
    expect(weekDays('2026-05-11')).toEqual([
      '2026-05-11', '2026-05-12', '2026-05-13', '2026-05-14', '2026-05-15', '2026-05-16', '2026-05-17',
    ])
  })
})
```

- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.

- [ ] **Step 3: Implement weekRange**

```ts
// web/src/features/calendar/weekRange.ts
function parse(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}
function fmt(date: Date): string {
  return date.toISOString().slice(0, 10)
}
export function mondayOf(iso: string): string {
  const d = parse(iso)
  const dow = (d.getUTCDay() + 6) % 7 // 0 = segunda
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

> NOTE: o teste de `weekRange` não usa `Date.now()`; passa datas fixas. Não introduzir relógio.

- [ ] **Step 4: Write failing CalendarGrid test**

```tsx
// web/src/features/calendar/CalendarGrid.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CalendarDay, WeekSummary } from '../../api/types'
import { CalendarGrid } from './CalendarGrid'

const days: CalendarDay[] = [
  { date: '2026-05-12', planned: [{ id: 'p1', planned_date: '2026-05-12', name: 'Z2', workout_type: 'ENDURANCE', planned_duration_s: 3600, planned_tss: 80, description: null, structure: null, adjustment: null }], completed: [], races: [{ id: 'r1', name: 'WOS Canastra', race_date: '2026-05-20', days_until: 8 }] },
]
const weeks: WeekSummary[] = [{ week_start: '2026-05-11', ctl: 12, atl: 45, tsb: -12, total_duration_s: 3600, total_tss: 80, total_distance_m: 0, total_elevation_m: 0, total_kj: 0 }]

describe('CalendarGrid', () => {
  it('renderiza card e marcador de prova', () => {
    render(<CalendarGrid days={days} weeks={weeks} onOpenWorkout={() => {}} />)
    expect(screen.getByText('🚴 Z2')).toBeInTheDocument()
    expect(screen.getByText(/WOS Canastra/)).toBeInTheDocument()
    expect(screen.getByText(/8 DAYS/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 5: Run to verify it fails** — Expected: FAIL.

- [ ] **Step 6: Implement CalendarGrid**

```tsx
// web/src/features/calendar/CalendarGrid.tsx
import type { CalendarDay, WeekSummary } from '../../api/types'
import { SummaryColumn } from './SummaryColumn'
import { WorkoutCard } from './WorkoutCard'
import { mondayOf, weekDays } from './weekRange'

const DOW = ['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB', 'DOM']

function RaceFlag({ name, daysUntil }: { name: string; daysUntil: number }) {
  return (
    <div className="rounded border border-blue-300 bg-blue-50 p-1 text-xs text-blue-800">
      <div className="font-semibold">{daysUntil} DAYS UNTIL EVENT</div>
      <div className="truncate">🏁 {name}</div>
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
              <div key={iso} className="min-h-32 space-y-1 rounded bg-white/50 p-1">
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
            : <div className="border-l" />}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 7: Run to verify it passes** — Expected: PASS.

- [ ] **Step 8: Implement CalendarPage (no separate test; covered by E2E later)**

```tsx
// web/src/features/calendar/CalendarPage.tsx
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCalendar } from '../../api/hooks'
import { mondayOf, weekDays } from './weekRange'
import { CalendarGrid } from './CalendarGrid'

export function CalendarPage({ todayIso }: { todayIso: string }) {
  const monday = mondayOf(todayIso)
  const days = useMemo(() => weekDays(monday), [monday])
  const start = days[0]
  const end = days[6]
  const navigate = useNavigate()
  const { data, isLoading, isError } = useCalendar(start, end)

  if (isLoading) return <p className="text-sm text-slate-500">Carregando…</p>
  if (isError || !data) return <p className="text-sm text-red-600">Erro ao carregar o calendário.</p>
  return <CalendarGrid days={data.days} weeks={data.weeks} onOpenWorkout={(id) => navigate(`/calendar/workout/${id}`)} />
}
```

> `todayIso` é injetado pelo chamador (App), nunca `new Date()` dentro de lógica testável; o App pode computar a data atual uma vez na borda.

- [ ] **Step 9: Commit**

```bash
git add web/src/features/calendar/weekRange.ts web/src/features/calendar/weekRange.test.ts web/src/features/calendar/CalendarGrid.tsx web/src/features/calendar/CalendarGrid.test.tsx web/src/features/calendar/CalendarPage.tsx
git commit -m "feat(web): CalendarGrid (semana 7col + summary + provas) e CalendarPage"
```

---

## Phase 6 — Detalhe do treino

### Task 14: `IntensityProfile` (planejado SVG + executado uPlot)

**Files:**
- Create: `web/src/features/workout/IntensityProfile.tsx`, `web/src/features/workout/profileData.ts`
- Test: `web/src/features/workout/profileData.test.ts`

**Interfaces:**
- Consumes: `Segment` (de `structureToSegments`), `WorkoutStreams`, `zoneColor`, `powerToZone`.
- Produces:
  - `streamToBars(power: Array<number | null>, ftp: number): Array<{ value: number; zone: number }>` — para barras coloridas do executado (zona por ponto).
  - `IntensityProfile({ segments, streams, ftp }: { segments: Segment[]; streams?: WorkoutStreams | null; ftp: number })` — se houver `streams.power`, desenha o stream (uPlot); senão, desenha os `segments` planejados (SVG em degraus). Não quebra sem dados (render vazio).

- [ ] **Step 1: Write the failing pure test**

```ts
// web/src/features/workout/profileData.test.ts
import { describe, expect, it } from 'vitest'
import { streamToBars } from './profileData'

describe('streamToBars', () => {
  it('mapeia cada ponto à sua zona, ignorando null', () => {
    const bars = streamToBars([null, 150, 300], 300)
    expect(bars).toEqual([
      { value: 0, zone: 1 },
      { value: 150, zone: 1 },
      { value: 300, zone: 4 },
    ])
  })
})
```

- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.

- [ ] **Step 3: Implement profileData**

```ts
// web/src/features/workout/profileData.ts
import { powerToZone } from '../../lib/zones'

export function streamToBars(power: Array<number | null>, ftp: number): Array<{ value: number; zone: number }> {
  return power.map((p) => {
    const v = p ?? 0
    return { value: v, zone: powerToZone(v, ftp) }
  })
}
```

- [ ] **Step 4: Implement IntensityProfile**

```tsx
// web/src/features/workout/IntensityProfile.tsx
import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { WorkoutStreams } from '../../api/types'
import type { Segment } from '../../lib/structure'
import { zoneColor } from '../../lib/zones'

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

function StreamPlot({ streams }: { streams: WorkoutStreams }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const xs = streams.power.map((_, i) => i)
    const ys = streams.power.map((p) => p ?? 0)
    const opts: uPlot.Options = {
      width: ref.current.clientWidth || 600, height: 140,
      scales: { x: { time: false } },
      series: [{}, { stroke: '#1d4ed8', width: 1, fill: 'rgba(29,78,216,0.15)' }],
      axes: [{ show: false }, { size: 30 }],
      legend: { show: false },
    }
    const plot = new uPlot(opts, [xs, ys], ref.current)
    return () => plot.destroy()
  }, [streams])
  return <div ref={ref} aria-label="Perfil executado" />
}

export function IntensityProfile({ segments, streams }: { segments: Segment[]; streams?: WorkoutStreams | null; ftp: number }) {
  if (streams && streams.power.length > 0) return <StreamPlot streams={streams} />
  if (segments.length > 0) return <PlannedSvg segments={segments} />
  return <div className="text-xs text-slate-400">Sem dados de intensidade.</div>
}
```

> O teste cobre `streamToBars` (puro). O componente uPlot é validado no E2E (Task 16). Não criar teste de DOM para uPlot (precisa de canvas/medições não confiáveis no jsdom).

- [ ] **Step 5: Run to verify the pure test passes** — `cd web && npm test`. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/workout/profileData.ts web/src/features/workout/profileData.test.ts web/src/features/workout/IntensityProfile.tsx
git commit -m "feat(web): IntensityProfile (planejado SVG + executado uPlot)"
```

---

### Task 15: `WorkoutDetailDrawer` + roteamento + shell de auth

**Files:**
- Create: `web/src/features/workout/WorkoutDetailDrawer.tsx`, `web/src/features/workout/StepsBreakdown.tsx`, `web/src/features/workout/PlannedCompletedTable.tsx`
- Modify: `web/src/App.tsx` (rotas + auth gate)
- Test: `web/src/features/workout/StepsBreakdown.test.tsx`, `web/src/features/workout/PlannedCompletedTable.test.tsx`

**Interfaces:**
- Consumes: `structureToSegments`, `structureToSteps`, `useWorkoutStreams`, `IntensityProfile`, `formatDuration`, `PlannedWorkout`, `CompletedWorkout`.
- Produces:
  - `StepsBreakdown({ steps })` — lista "Label · N min @ X–Y W · Zona Z".
  - `PlannedCompletedTable({ planned, completed })` — tabela Planned×Completed (Duração, Distância, TSS, IF, NP, Work/kJ, El. Gain).
  - `WorkoutDetailDrawer({ planned, completed, onClose })` — cabeçalho + `IntensityProfile` + tabela + Min/Avg/Max + steps + painel de ajuste-IA (se `planned.adjustment`).
  - `App` com `BrowserRouter`: rota `/` (CalendarPage) e `/calendar/workout/:id` (drawer); gate de login.

- [ ] **Step 1: Write failing StepsBreakdown test**

```tsx
// web/src/features/workout/StepsBreakdown.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StepsBreakdown } from './StepsBreakdown'

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

- [ ] **Step 2: Write failing PlannedCompletedTable test**

```tsx
// web/src/features/workout/PlannedCompletedTable.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CompletedWorkout, PlannedWorkout } from '../../api/types'
import { PlannedCompletedTable } from './PlannedCompletedTable'

const planned = { planned_duration_s: 6840, planned_tss: 103 } as PlannedWorkout
const completed = { duration_s: 6800, tss: 103, intensity_factor: 0.74, normalized_power: 222, kj: 1434, distance_m: 51400, elevation_gain_m: 300 } as CompletedWorkout

describe('PlannedCompletedTable', () => {
  it('mostra colunas planejado e executado', () => {
    render(<PlannedCompletedTable planned={planned} completed={completed} />)
    expect(screen.getByText('Planned')).toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.getByText('1:54:00')).toBeInTheDocument() // planned duration
    expect(screen.getByText('0.74')).toBeInTheDocument()    // IF
  })
})
```

- [ ] **Step 3: Run to verify both fail** — Expected: FAIL.

- [ ] **Step 4: Implement StepsBreakdown**

```tsx
// web/src/features/workout/StepsBreakdown.tsx
type Step = { label: string; durationS: number; lowW: number | null; highW: number | null; zone: number }

export function StepsBreakdown({ steps }: { steps: Step[] }) {
  return (
    <ul className="space-y-2">
      {steps.map((s, i) => (
        <li key={i} className="text-sm">
          <span className="font-semibold">{s.label}</span>{' · '}
          <span>{Math.round(s.durationS / 60)} min</span>
          {s.lowW != null && s.highW != null && <span>{' @ '}{s.lowW}–{s.highW} W</span>}
          <span className="text-slate-500">{' · Zona '}{s.zone}</span>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 5: Implement PlannedCompletedTable**

```tsx
// web/src/features/workout/PlannedCompletedTable.tsx
import type { CompletedWorkout, PlannedWorkout } from '../../api/types'
import { formatDistanceKm, formatDuration } from '../../lib/format'

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
          <tr key={k} className="border-t">
            <td className="py-1 text-slate-500">{k}</td><td className="py-1">{p}</td><td className="py-1 font-medium">{c}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
```

- [ ] **Step 6: Implement WorkoutDetailDrawer**

```tsx
// web/src/features/workout/WorkoutDetailDrawer.tsx
import { useWorkoutStreams } from '../../api/hooks'
import type { CompletedWorkout, PlannedWorkout } from '../../api/types'
import { structureToSegments, structureToSteps } from '../../lib/structure'
import { IntensityProfile } from './IntensityProfile'
import { PlannedCompletedTable } from './PlannedCompletedTable'
import { StepsBreakdown } from './StepsBreakdown'

export function WorkoutDetailDrawer({
  planned, completed, onClose,
}: { planned: PlannedWorkout | null; completed: CompletedWorkout | null; onClose: () => void }) {
  const streams = useWorkoutStreams(completed?.id ?? null)
  const ftp = planned?.structure?.ftp_watts ?? 250
  const segments = structureToSegments(planned?.structure ?? null, ftp)
  const steps = structureToSteps(planned?.structure ?? null, ftp)
  const title = planned?.name ?? completed?.name ?? 'Treino'

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <aside className="h-full w-full max-w-2xl overflow-y-auto bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button type="button" onClick={onClose} className="text-slate-500" aria-label="Fechar">✕</button>
        </div>
        <IntensityProfile segments={segments} streams={streams.data} ftp={ftp} />
        {planned?.adjustment && (
          <div className="my-3 rounded border border-violet-200 bg-violet-50 p-2 text-sm text-violet-800">
            🤖 Treino ajustado pela IA. Valores efetivos refletem o ajuste do dia.
          </div>
        )}
        <div className="my-4"><PlannedCompletedTable planned={planned} completed={completed} /></div>
        {completed && (
          <div className="my-4 grid grid-cols-3 gap-2 text-sm">
            <div><div className="text-xs text-slate-400">Avg Power</div><div>{completed.avg_power != null ? `${Math.round(completed.avg_power)} W` : '—'}</div></div>
            <div><div className="text-xs text-slate-400">Avg HR</div><div>{completed.avg_hr != null ? `${Math.round(completed.avg_hr)} bpm` : '—'}</div></div>
            <div><div className="text-xs text-slate-400">NP</div><div>{completed.normalized_power != null ? `${Math.round(completed.normalized_power)} W` : '—'}</div></div>
          </div>
        )}
        {steps.length > 0 && (
          <div className="my-4">
            <h3 className="mb-2 text-sm font-semibold">Workout Details</h3>
            <StepsBreakdown steps={steps} />
          </div>
        )}
        {(planned?.description || completed?.notes) && (
          <p className="my-2 text-sm text-slate-600">{planned?.description ?? completed?.notes}</p>
        )}
      </aside>
    </div>
  )
}
```

- [ ] **Step 7: Wire routing + auth gate in App**

```tsx
// web/src/App.tsx
import { useMemo } from 'react'
import { BrowserRouter, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { AppShell } from './AppShell'
import { useCalendar } from './api/hooks'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { LoginPage } from './auth/LoginPage'
import { CalendarPage } from './features/calendar/CalendarPage'
import { WorkoutDetailDrawer } from './features/workout/WorkoutDetailDrawer'
import { mondayOf, weekDays } from './features/calendar/weekRange'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function WorkoutRoute({ todayIso }: { todayIso: string }) {
  const { id } = useParams()
  const navigate = useNavigate()
  const days = useMemo(() => weekDays(mondayOf(todayIso)), [todayIso])
  const { data } = useCalendar(days[0], days[6])
  if (!id || !data) return null
  let planned = null
  let completed = null
  for (const d of data.days) {
    completed = d.completed.find((c) => c.id === id) ?? completed
    planned = d.planned.find((p) => p.id === id) ?? planned
    if (completed) { planned = d.planned.find((p) => p.workout_type === completed!.workout_type) ?? planned }
  }
  return <WorkoutDetailDrawer planned={planned} completed={completed} onClose={() => navigate('/')} />
}

function AuthedApp() {
  const { user } = useAuth()
  const today = todayIso()
  return (
    <AppShell user={user ?? undefined}>
      <CalendarPage todayIso={today} />
      <Routes>
        <Route path="/calendar/workout/:id" element={<WorkoutRoute todayIso={today} />} />
        <Route path="*" element={null} />
      </Routes>
    </AppShell>
  )
}

function Gate() {
  const { token } = useAuth()
  return token ? <AuthedApp /> : <LoginPage />
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Gate />
      </BrowserRouter>
    </AuthProvider>
  )
}
```

> The smoke test from Task 4 (`App.test.tsx`) asserted a static `<h1>Calendário</h1>`. Update it to render within providers and assert the shell renders the login form when unauthenticated (no token in jsdom localStorage):
> ```tsx
> // web/src/App.test.tsx (replace body)
> import { render, screen } from '@testing-library/react'
> import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
> import { beforeEach, describe, expect, it } from 'vitest'
> import { App } from './App'
> describe('App', () => {
>   beforeEach(() => localStorage.clear())
>   it('mostra login quando sem token', () => {
>     const qc = new QueryClient()
>     render(<QueryClientProvider client={qc}><App /></QueryClientProvider>)
>     expect(screen.getByRole('button', { name: 'Entrar' })).toBeInTheDocument()
>   })
> })
> ```
> Also wrap `main.tsx`'s `<App/>` is already inside `QueryClientProvider` — keep it; remove the duplicate `QueryClientProvider` if both exist (App provides Router+Auth, main provides Query).

- [ ] **Step 8: Run all frontend tests**

Run: `cd web && npm test`
Expected: PASS (all suites green, incl. updated App smoke).

- [ ] **Step 9: Commit**

```bash
git add web/src/features/workout web/src/App.tsx web/src/App.test.tsx
git commit -m "feat(web): drawer de detalhe do treino + roteamento + auth gate"
```

---

## Phase 7 — Deployment

### Task 16: Serviço Docker `web` (build + nginx + compose)

**Files:**
- Create: `web/Dockerfile`, `web/nginx.conf`, `web/.dockerignore`
- Modify: `docker-compose.yml` (novo serviço `web`)

**Interfaces:**
- Produces: imagem que builda a SPA e serve estático via nginx, com proxy `/api` → serviço `api`.

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# web/Dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

- [ ] **Step 2: Create nginx.conf**

```nginx
# web/nginx.conf
server {
  listen 80;
  location /api/ {
    proxy_pass http://api:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }
  location / {
    root /usr/share/nginx/html;
    try_files $uri /index.html;  # SPA fallback
  }
}
```

- [ ] **Step 3: Create .dockerignore**

```
# web/.dockerignore
node_modules
dist
```

- [ ] **Step 4: Add the compose service**

In `docker-compose.yml`, add a `web` service alongside `frontend` (Streamlit). Match the existing indentation/network of the `api` service.

```yaml
  web:
    build: ./web
    ports:
      - "5174:80"
    depends_on:
      - api
```

- [ ] **Step 5: Build and smoke-check**

Run: `docker compose build web && docker compose up -d web && curl -sI http://localhost:5174 | head -1`
Expected: `HTTP/1.1 200 OK` and the SPA loads (login screen) at http://localhost:5174.

- [ ] **Step 6: Commit**

```bash
git add web/Dockerfile web/nginx.conf web/.dockerignore docker-compose.yml
git commit -m "feat(web): serviço docker web (build Vite + nginx + proxy /api) ao lado do Streamlit"
```

---

## Verificação final do ciclo

- Backend: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_repositories app/tests/test_api/test_calendar.py app/tests/test_api/test_workout_streams.py app/tests/test_metrics/test_downsample.py -q"` → tudo verde.
- Frontend: `cd web && npm test` → todas as suites verdes.
- Manual: `docker compose up -d --build api web` → abrir http://localhost:5174, logar com o atleta de validação, ver a semana com cards + summary + provas, clicar num treino e ver o detalhe com gráfico + tabela + steps.

## Self-review (cobertura do spec)

- §3 stack / §4 deployment → Tasks 4, 16. ✓
- §5.1 `/calendar` → Tasks 1–2. ✓
- §5.2 `/workouts/{id}/streams` → Task 3. ✓
- §6 calendário (cards, summary, provas, IA badge) → Tasks 11–13. ✓ (linha Metrics/Sleep deferida por design — §2).
- §7 detalhe (perfil, tabela, min/avg/max, steps, painel IA) → Tasks 14–15. ✓
- §8 lógica pura (zones, compliance, structure, format) → Tasks 6–9. ✓
- §9 fluxo de dados (auth→token→hooks) → Tasks 5, 10, 15. ✓
- §10 testes → testes em todas as tasks; E2E Playwright marcado como opcional (não bloqueia o ciclo; pode virar task futura).
- Nota: a edição manual de treino planejado e drag-and-drop ficam fora (não-objetivos §2).
