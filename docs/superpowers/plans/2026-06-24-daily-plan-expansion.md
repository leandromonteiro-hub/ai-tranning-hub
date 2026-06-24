# Daily Plan Expansion (treinos diários até a prova) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) tracking.

**Goal:** Expandir um plano periodizado em um treino planejado por dia (de hoje até a prova), cada dia com tipo/duração/TSS e treino estruturado exportável (.zwo/.fit), por regra (sem IA), idempotente, com botão no frontend.

**Architecture:** Núcleo puro `plan_expander.allocate_days(weeks, ftp, rest_per_week)` decide os dias (tipo + estrutura + TSS) reusando `app/services/workout/templates.py`; um serviço de persistência idempotente grava `workouts_planned` com `source_plan_id` (migração 0007); um endpoint `POST /plans/{plan_id}/expand`; export por dia; e um botão na aba Plano do Streamlit.

**Tech Stack:** FastAPI/SQLAlchemy async, Pydantic, pytest. Backend test cmd (raiz): `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -v"`. Frontend sintaxe: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); print('ok')"`.

## Global Constraints

- **Geração por regra** (sem IA). Tenant-scoped por `ctx.athlete_id`; isolamento entre atletas obrigatório.
- **Descanso/semana:** `7 - AthleteProfile.weekly_days` se `weekly_days` preenchido (clamp 0..3); senão **1**.
- **Idempotência:** re-expandir um plano apaga os `workouts_planned` com aquele `source_plan_id` e recria; treinos com `source_plan_id` nulo (manuais/recomendações) NÃO são tocados.
- **Reuso obrigatório:** `app/services/workout/templates.py` (`endurance/sweet_spot/vo2max/recovery/openers`, todas `(ftp_watts)->StructuredWorkout`), `workout/analysis.py` (`estimated_tss`, `total_duration_s`), `workout/model.py` (`StructuredWorkout` Pydantic; `.model_dump()`/`.model_validate()`), `workout/zwo_encoder.encode_zwo`, `workout/fit_encoder.encode`.
- **Enums:** `BlockType {BASE,BUILD,PEAK,TAPER,RECOVERY}`, `WorkoutType {ENDURANCE,TEMPO,SWEET_SPOT,THRESHOLD,VO2MAX,RECOVERY,...}` (`app/models/enums.py`).
- **Janela:** de `max(plan.start_date, hoje)` até `plan.race_date` inclusive. `race_date < hoje` → 400.
- Código em inglês; descrições do treino em português. Commits frequentes, um por task.

## Allocation rules (v1, documentadas)

Para cada semana do plano, escolher `7 - rest_per_week` dias de treino (descanso nos primeiros `rest_per_week` dias da semana — determinístico) e atribuir a cada dia de treino um papel por `block_type`:
- **BASE:** dia do meio = `sweet_spot`; demais = `endurance`.
- **BUILD:** 2 dias de qualidade = `vo2max` e `sweet_spot`; demais = `endurance`.
- **PEAK:** 2 dias de qualidade = `vo2max`; demais = `endurance` (volume menor).
- **TAPER:** 1 dia = `openers`; 1 dia = `endurance` curto; resto descanso.
- **semana de recuperação** (`is_recovery_week=True`): todos = `recovery`.
Os dias de **endurance** têm a duração **escalada** para distribuir o TSS restante da semana (alvo semanal = `week.planned_tss`; subtrai-se o TSS dos dias de qualidade fixos; o restante é dividido pelos dias de endurance; a duração do passo "active" do endurance é ajustada para atingir o TSS-alvo do dia). Dias de qualidade usam o TSS natural do template. `workout_type` do `workouts_planned` reflete o papel.

---

### Task 1: Migração 0007 + `source_plan_id` em `workouts_planned`

**Files:**
- Modify: `backend/app/models/workout.py` (classe `WorkoutPlanned`)
- Create: `backend/alembic/versions/0007_workout_planned_source_plan.py`
- Test: `backend/app/tests/test_api/test_workout_planned_source.py`

**Interfaces:**
- Produces: `WorkoutPlanned.source_plan_id: uuid.UUID | None` (FK `training_plans.id`).

- [ ] **Step 1: Teste que falha** — `backend/app/tests/test_api/test_workout_planned_source.py` (espelhar a fixture sqlite em memória de `backend/app/tests/test_api/test_workout_extra.py`): inserir um `WorkoutPlanned` com `source_plan_id=<uuid de um TrainingPlan inserido>`, commit, re-query, asserir round-trip; e inserir um com `source_plan_id=None` (nullable).

- [ ] **Step 2: Rodar → FALHA** (`source_plan_id` não existe). Cmd: `... pytest app/tests/test_api/test_workout_planned_source.py -v`

- [ ] **Step 3: Adicionar a coluna** — em `WorkoutPlanned` (após `source_recommendation_id`):
```python
    source_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_plans.id"), nullable=True, index=True
    )
```
(`ForeignKey`, `uuid`, `Mapped`, `mapped_column` já estão importados em `workout.py`.)

- [ ] **Step 4: Migração 0007** — `backend/alembic/versions/0007_workout_planned_source_plan.py` (espelhar 0005/0006; `down_revision="0006"`):
```python
"""Add source_plan_id to workouts_planned.

Revision ID: 0007
Revises: 0006
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workouts_planned",
        sa.Column("source_plan_id", sa.Uuid(), sa.ForeignKey("training_plans.id"), nullable=True),
    )
    op.create_index("ix_workouts_planned_source_plan_id", "workouts_planned", ["source_plan_id"])


def downgrade() -> None:
    op.drop_index("ix_workouts_planned_source_plan_id", table_name="workouts_planned")
    op.drop_column("workouts_planned", "source_plan_id")
```
(Confirmar o tipo de coluna UUID usado nas outras migrações — se 0001 usa `sa.Uuid()` vs um helper, seguir o mesmo padrão.)

- [ ] **Step 5: Rodar teste + suíte** — `... pytest app/tests/test_api/test_workout_planned_source.py -v && python -m pytest -q` → verde.

- [ ] **Step 6: Commit** — `git add backend/app/models/workout.py backend/alembic/versions/0007_workout_planned_source_plan.py backend/app/tests/test_api/test_workout_planned_source.py && git commit -m "feat(plan): add source_plan_id to workouts_planned (+migration 0007)"`

---

### Task 2: Núcleo puro `allocate_days`

**Files:**
- Create: `backend/app/services/planning/plan_expander.py`
- Test: `backend/app/tests/test_planning/test_plan_expander.py` (criar `__init__.py` se faltar)

**Interfaces:**
- Consumes: `app.services.workout.templates` (`endurance/sweet_spot/vo2max/recovery/openers`), `app.services.workout.analysis` (`estimated_tss`), `app.services.workout.model.StructuredWorkout`, `app.models.enums.BlockType`/`WorkoutType`.
- Produces: `@dataclass WeekSpec {week_start: date, block_type: BlockType, planned_tss: float, is_recovery_week: bool}`; `@dataclass DailyPlanned {planned_date: date, workout_type: WorkoutType, planned_duration_s: int, planned_tss: float, description: str, structure: dict}`; `allocate_days(weeks: list[WeekSpec], ftp: float, race_date: date, rest_per_week: int, today: date) -> list[DailyPlanned]`.

- [ ] **Step 1: Teste que falha** — `test_plan_expander.py`:
```python
from datetime import date
from app.models.enums import BlockType, WorkoutType
from app.services.planning.plan_expander import WeekSpec, allocate_days


def _weeks() -> list[WeekSpec]:
    return [
        WeekSpec(date(2026, 1, 5), BlockType.BASE, 500.0, False),   # seg-dom
        WeekSpec(date(2026, 1, 12), BlockType.BUILD, 600.0, False),
    ]


def test_rest_days_per_week():
    days = allocate_days(_weeks(), ftp=300.0, race_date=date(2026, 1, 18),
                         rest_per_week=1, today=date(2026, 1, 5))
    # 2 semanas × 6 dias de treino = 12 (jan 18 é o fim da 2a semana)
    assert len(days) == 12


def test_base_week_has_one_quality():
    days = allocate_days(_weeks()[:1], ftp=300.0, race_date=date(2026, 1, 11),
                         rest_per_week=1, today=date(2026, 1, 5))
    quality = [d for d in days if d.workout_type in (WorkoutType.SWEET_SPOT, WorkoutType.VO2MAX, WorkoutType.THRESHOLD)]
    assert len(quality) == 1
    assert all(d.structure and d.planned_tss > 0 for d in days)


def test_window_stops_at_race():
    days = allocate_days(_weeks(), ftp=300.0, race_date=date(2026, 1, 14),
                         rest_per_week=1, today=date(2026, 1, 5))
    assert max(d.planned_date for d in days) <= date(2026, 1, 14)


def test_starts_at_today_not_before():
    days = allocate_days(_weeks(), ftp=300.0, race_date=date(2026, 1, 18),
                         rest_per_week=1, today=date(2026, 1, 8))
    assert min(d.planned_date for d in days) >= date(2026, 1, 8)
```

- [ ] **Step 2: Rodar → FALHA** (módulo inexistente). Cmd: `... pytest app/tests/test_planning/test_plan_expander.py -v`

- [ ] **Step 3: Implementar** — `backend/app/services/planning/plan_expander.py`:
```python
"""Rule-based expansion of a periodized plan into daily planned workouts.

Pure core (no DB): given the plan's weeks + FTP, decide one structured workout
per training day. Reuses app.services.workout templates so each day is a real,
exportable structured workout. See the plan doc for the allocation rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.models.enums import BlockType, WorkoutType
from app.services.workout import analysis, templates
from app.services.workout.model import StructuredWorkout


@dataclass
class WeekSpec:
    week_start: date
    block_type: BlockType
    planned_tss: float
    is_recovery_week: bool


@dataclass
class DailyPlanned:
    planned_date: date
    workout_type: WorkoutType
    planned_duration_s: int
    planned_tss: float
    description: str
    structure: dict


# Role -> (template fn, WorkoutType)
_ROLE_ENDURANCE = (templates.endurance, WorkoutType.ENDURANCE)
_ROLE_SWEET = (templates.sweet_spot, WorkoutType.SWEET_SPOT)
_ROLE_VO2 = (templates.vo2max, WorkoutType.VO2MAX)
_ROLE_RECOVERY = (templates.recovery, WorkoutType.RECOVERY)
_ROLE_OPENERS = (templates.openers, WorkoutType.VO2MAX)

# Quality day positions (index among the week's training days) per block type.
_QUALITY_BY_BLOCK: dict[BlockType, list[tuple]] = {
    BlockType.BASE: [(1, _ROLE_SWEET)],
    BlockType.BUILD: [(0, _ROLE_VO2), (2, _ROLE_SWEET)],
    BlockType.PEAK: [(0, _ROLE_VO2), (2, _ROLE_VO2)],
    BlockType.TAPER: [(0, _ROLE_OPENERS)],
    BlockType.RECOVERY: [],
}


def _scaled_endurance(ftp: float, target_tss: float) -> StructuredWorkout:
    """Endurance workout whose duration is scaled to approximate target_tss."""
    w = templates.endurance(ftp)
    base_tss = analysis.estimated_tss(w)
    if base_tss <= 0 or target_tss <= 0:
        return w
    factor = max(0.5, min(2.5, target_tss / base_tss))
    # Scale the single long "active" step's duration (warmup/cooldown unchanged).
    for el in w.elements:
        if getattr(el, "intensity", None) == "active":
            el.duration_s = int(el.duration_s * factor)
    return w


def allocate_days(
    weeks: list[WeekSpec], ftp: float, race_date: date, rest_per_week: int, today: date
) -> list[DailyPlanned]:
    rest_per_week = max(0, min(3, rest_per_week))
    out: list[DailyPlanned] = []
    for wk in weeks:
        day_dates = [wk.week_start + timedelta(days=i) for i in range(7)]
        day_dates = [d for d in day_dates if today <= d <= race_date]
        if not day_dates:
            continue
        # First rest_per_week days of the (visible) week are rest.
        training = day_dates[rest_per_week:] if len(day_dates) > rest_per_week else []
        # Recovery week: all easy recovery.
        if wk.is_recovery_week:
            for d in training:
                out.append(_make(d, ftp, _ROLE_RECOVERY))
            continue
        quality_positions = dict(_QUALITY_BY_BLOCK.get(wk.block_type, []))
        quality_tss = 0.0
        endurance_idx: list[int] = []
        roles: dict[int, tuple] = {}
        for i in range(len(training)):
            if i in quality_positions:
                roles[i] = quality_positions[i]
            else:
                endurance_idx.append(i)
        # Estimate quality TSS to distribute the remainder to endurance days.
        for i, role in roles.items():
            quality_tss += analysis.estimated_tss(role[0](ftp))
        remaining = max(0.0, wk.planned_tss - quality_tss)
        per_endurance = remaining / len(endurance_idx) if endurance_idx else 0.0
        for i, d in enumerate(training):
            if i in roles:
                out.append(_make(d, ftp, roles[i]))
            else:
                w = _scaled_endurance(ftp, per_endurance)
                w.ftp_watts = ftp
                w.estimated_tss = analysis.estimated_tss(w)
                out.append(_daily_from(d, w, WorkoutType.ENDURANCE))
    return out


def _make(d: date, ftp: float, role: tuple) -> DailyPlanned:
    fn, wtype = role
    w = fn(ftp)
    w.ftp_watts = ftp
    w.estimated_tss = analysis.estimated_tss(w)
    return _daily_from(d, w, wtype)


def _daily_from(d: date, w: StructuredWorkout, wtype: WorkoutType) -> DailyPlanned:
    return DailyPlanned(
        planned_date=d,
        workout_type=wtype,
        planned_duration_s=analysis.total_duration_s(w),
        planned_tss=round(analysis.estimated_tss(w), 1),
        description=analysis.describe(w),
        structure=w.model_dump(),
    )
```

- [ ] **Step 4: Rodar → PASSA.** Cmd igual ao Step 2. (Se `templates.openers`/`vo2max` etc. diferirem, ajustar imports conforme `templates.py` real.)

- [ ] **Step 5: Commit** — `git add backend/app/services/planning/plan_expander.py backend/app/tests/test_planning/ && git commit -m "feat(plan): pure allocate_days — rule-based daily expansion of a plan"`

---

### Task 3: Persistência idempotente + endpoint `POST /plans/{plan_id}/expand`

**Files:**
- Modify: `backend/app/services/planning/plan_expander.py` (add `expand_plan_to_daily`)
- Modify: `backend/app/api/routes/plans.py` (novo endpoint)
- Modify: `backend/app/schemas/training_plan.py` (schema de resposta)
- Test: `backend/app/tests/test_api/test_plan_expand.py`

**Interfaces:**
- Consumes: `allocate_days`; `app.models.training_plan.TrainingPlan/TrainingWeek`; `app.models.workout.WorkoutPlanned`; `app.repositories.metrics_repo.FtpRepository.value_on(date, athlete_id)`; `get_tenant`/`get_db`.
- Produces: `async def expand_plan_to_daily(session, ctx, athlete_id, plan_id) -> dict`; `POST /plans/{plan_id}/expand`.

- [ ] **Step 1: Teste que falha** — `test_plan_expand.py` (fixture ASGI httpx + sqlite como `test_api/test_anamnese.py`; semear 2 atletas A/B, FTP para A, e gerar um plano para A via `POST /plans/generate` com uma prova futura — ou inserir TrainingPlan+TrainingWeek direto). Asserir:
  - `POST /api/v1/plans/{plan_id}/expand` (auth A) → 200; cria `WorkoutPlanned` com `source_plan_id=plan_id` cobrindo dias até a prova;
  - segunda chamada → idempotente (contagem de `workouts_planned` estável);
  - atleta B tem 0 `workouts_planned` (isolamento);
  - plano com prova no passado → 400.

- [ ] **Step 2: Rodar → FALHA.** Cmd: `... pytest app/tests/test_api/test_plan_expand.py -v`

- [ ] **Step 3: `expand_plan_to_daily`** em `plan_expander.py`:
```python
async def expand_plan_to_daily(session, ctx, athlete_id, plan_id):
    from datetime import date as _date
    from sqlalchemy import delete, select
    from app.models.training_plan import TrainingPlan, TrainingWeek
    from app.models.workout import WorkoutPlanned
    from app.repositories.metrics_repo import FtpRepository

    plan = (await session.execute(
        select(TrainingPlan).where(
            TrainingPlan.id == plan_id,
            TrainingPlan.athlete_id == athlete_id,
            TrainingPlan.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if plan is None:
        return {"error": "not_found"}
    today = _date.today()
    if plan.race_date < today:
        return {"error": "race_past"}

    weeks_rows = (await session.execute(
        select(TrainingWeek).where(TrainingWeek.plan_id == plan_id).order_by(TrainingWeek.week_index)
    )).scalars().all()
    weeks = [WeekSpec(w.week_start, w.block_type, w.planned_tss or 0.0, bool(w.is_recovery_week)) for w in weeks_rows]

    ftp = await FtpRepository(session, ctx).value_on(today, athlete_id) or 200.0

    # rest_per_week from the athlete profile (weekly_days), else 1.
    from app.services.ai.profile_context import fetch_profile
    profile = await fetch_profile(session, athlete_id)
    rest = 1
    if profile is not None and profile.weekly_days:
        rest = max(0, min(3, 7 - int(profile.weekly_days)))

    days = allocate_days(weeks, ftp=ftp, race_date=plan.race_date, rest_per_week=rest, today=today)

    # Idempotent replace: drop this plan's existing daily rows, recreate.
    await session.execute(
        delete(WorkoutPlanned).where(
            WorkoutPlanned.athlete_id == athlete_id,
            WorkoutPlanned.source_plan_id == plan_id,
        )
    )
    for d in days:
        session.add(WorkoutPlanned(
            athlete_id=athlete_id, created_by=athlete_id,
            planned_date=d.planned_date, name=d.structure.get("name", "Treino"),
            workout_type=d.workout_type, planned_duration_s=d.planned_duration_s,
            planned_tss=d.planned_tss, structure=d.structure, description=d.description,
            source_plan_id=plan_id,
        ))
    await session.flush()
    return {
        "days": len(days),
        "tss_total": round(sum(d.planned_tss for d in days), 1),
        "start": str(min((d.planned_date for d in days), default=today)),
        "end": str(max((d.planned_date for d in days), default=today)),
    }
```
(Confirmar nos modelos reais os nomes `TrainingWeek.week_start/planned_tss/is_recovery_week/week_index` e `TrainingPlan.race_date` — ajustar se diferirem.)

- [ ] **Step 4: Schema + endpoint** — em `backend/app/schemas/training_plan.py` adicionar:
```python
class PlanExpandResult(BaseModel):
    days: int
    tss_total: float
    start: str
    end: str
```
Em `backend/app/api/routes/plans.py`:
```python
@router.post("/{plan_id}/expand", response_model=PlanExpandResult, status_code=201)
async def expand_plan(
    plan_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate one structured planned workout per day from the periodized plan
    until the race (rule-based, idempotent)."""
    result = await expand_plan_to_daily(db, ctx, ctx.athlete_id, plan_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    if result.get("error") == "race_past":
        raise HTTPException(status_code=400, detail="A prova já ocorreu")
    await db.commit()
    return PlanExpandResult(**result)
```
(Adicionar imports: `uuid`, `HTTPException`, `expand_plan_to_daily`, `PlanExpandResult`, `get_tenant` — conferir o que já existe em `plans.py`.)

- [ ] **Step 5: Rodar teste + suíte → PASSA.** Cmd: `... pytest app/tests/test_api/test_plan_expand.py -v && python -m pytest -q`

- [ ] **Step 6: Commit** — `git add backend/app/services/planning/plan_expander.py backend/app/api/routes/plans.py backend/app/schemas/training_plan.py backend/app/tests/test_api/test_plan_expand.py && git commit -m "feat(plan): POST /plans/{id}/expand — persist idempotent daily workouts"`

---

### Task 4: Export por dia (.zwo/.fit) de um treino planejado

**Files:**
- Modify: `backend/app/api/routes/plans.py` (rotas de export)
- Test: `backend/app/tests/test_api/test_plan_workout_export.py`

**Interfaces:**
- Consumes: `WorkoutPlanned.structure` (jsonb), `StructuredWorkout.model_validate`, `zwo_encoder.encode_zwo`, `fit_encoder.encode`.
- Produces: `GET /plans/workouts/{workout_planned_id}/export.zwo` e `.fit`.

- [ ] **Step 1: Teste que falha** — `test_plan_workout_export.py`: após expandir um plano (ou inserir um `WorkoutPlanned` com `structure` de um `StructuredWorkout.model_dump()`), `GET /api/v1/plans/workouts/{id}/export.zwo` → 200, `content-type` de download, corpo não-vazio; idem `.fit`; e um id de outro atleta → 404 (isolamento).

- [ ] **Step 2: Rodar → FALHA.** Cmd: `... pytest app/tests/test_api/test_plan_workout_export.py -v`

- [ ] **Step 3: Implementar as rotas** em `plans.py`:
```python
from fastapi import Response
from app.models.workout import WorkoutPlanned
from app.services.workout.model import StructuredWorkout
from app.services.workout.zwo_encoder import encode_zwo
from app.services.workout.fit_encoder import encode as encode_fit


async def _planned_workout(db, ctx, workout_planned_id) -> StructuredWorkout:
    row = (await db.execute(
        select(WorkoutPlanned).where(
            WorkoutPlanned.id == workout_planned_id,
            WorkoutPlanned.athlete_id == ctx.athlete_id,
            WorkoutPlanned.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if row is None or not row.structure:
        raise HTTPException(status_code=404, detail="Treino planejado não encontrado")
    return StructuredWorkout.model_validate(row.structure)


def _dl(data: bytes, name: str, ext: str) -> Response:
    return Response(
        content=data, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}.{ext}"'},
    )


@router.get("/workouts/{workout_planned_id}/export.zwo")
async def export_planned_zwo(workout_planned_id: uuid.UUID,
                             ctx: TenantContext = Depends(get_tenant),
                             db: AsyncSession = Depends(get_db)):
    w = await _planned_workout(db, ctx, workout_planned_id)
    return _dl(encode_zwo(w), "treino", "zwo")


@router.get("/workouts/{workout_planned_id}/export.fit")
async def export_planned_fit(workout_planned_id: uuid.UUID,
                             ctx: TenantContext = Depends(get_tenant),
                             db: AsyncSession = Depends(get_db)):
    w = await _planned_workout(db, ctx, workout_planned_id)
    return _dl(encode_fit(w), "treino", "fit")
```
(Conferir se `encode_zwo`/`encode_fit` retornam `bytes` ou `str` — em `recommendations.py` há `_download`; reusar o mesmo helper/pattern. Se `encode_zwo` retorna `str`, fazer `.encode()`.)

- [ ] **Step 4: Rodar teste → PASSA.** Cmd igual ao Step 2.

- [ ] **Step 5: Commit** — `git add backend/app/api/routes/plans.py backend/app/tests/test_api/test_plan_workout_export.py && git commit -m "feat(plan): per-day planned-workout export (.zwo/.fit)"`

---

### Task 5: Frontend — botão "Gerar treinos diários até a prova" + lista

**Files:**
- Modify: `frontend/app.py` (`plan_tab`)

**Interfaces:**
- Consumes: `api(...)`, `POST /plans/{id}/expand`, `GET /plans/workouts/{id}/export.{ext}`, `GET /workouts/planned` ou listagem dos `workouts_planned` (verificar se há rota; se não, usar o retorno do expand ou uma listagem nova — ver Step 1).

- [ ] **Step 1: Verificar rota de listagem dos treinos planejados** — checar `backend/app/api/routes/` por um `GET` de `workouts_planned` (ex.: em `plans.py` ou `workouts.py`). Se NÃO existir, adicionar em `plans.py`: `GET /plans/{plan_id}/workouts` → lista `WorkoutPlanned` com `source_plan_id=plan_id` (id, planned_date, workout_type, planned_duration_s, planned_tss, description), tenant-scoped, com schema `PlannedWorkoutRead`. (Se for adicionada, fazer como sub-passo TDD análogo à Task 3 e incluir no commit.)

- [ ] **Step 2: Adicionar ao `plan_tab`** em `frontend/app.py`, logo após o bloco que mostra o plano (`plan = _latest_plan(token)` / a tabela de semanas), inserir:
```python
    st.divider()
    st.markdown("#### Treinos diários até a prova")
    if st.button("Gerar treinos diários até a prova"):
        r = api("POST", f"/plans/{plan['id']}/expand", token=token)
        if r.status_code == 201:
            d = r.json()
            st.success(f"{d['days']} treinos gerados ({d['start']} → {d['end']}, TSS total {d['tss_total']}).")
            st.rerun()
        else:
            st.error(r.text)

    wl = api("GET", f"/plans/{plan['id']}/workouts", token=token)
    daily = wl.json() if wl.status_code == 200 else []
    if daily:
        import pandas as pd
        st.dataframe(pd.DataFrame([
            {"Data": w["planned_date"], "Tipo": w["workout_type"],
             "Min": round((w.get("planned_duration_s") or 0) / 60),
             "TSS": w.get("planned_tss")}
            for w in sorted(daily, key=lambda x: x["planned_date"])
        ]), hide_index=True, use_container_width=True)
        sel = st.selectbox("Baixar treino do dia", [w["planned_date"] for w in sorted(daily, key=lambda x: x["planned_date"])])
        chosen = next((w for w in daily if w["planned_date"] == sel), None)
        if chosen:
            c1, c2 = st.columns(2)
            for col, ext in ((c1, "zwo"), (c2, "fit")):
                resp = api("GET", f"/plans/workouts/{chosen['id']}/export.{ext}", token=token)
                if resp.status_code == 200:
                    col.download_button(f"⬇️ .{ext}", data=resp.content,
                                        file_name=f"treino_{sel}.{ext}",
                                        mime="application/octet-stream", key=f"dl_{ext}_{chosen['id']}")
```
(`pd` já é importado no topo do `app.py`; remover o `import pandas as pd` local se redundante.)

- [ ] **Step 3: Checar sintaxe** — `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); print('ok')"` → `ok`.

- [ ] **Step 4: Verificação ao vivo** — `docker compose up -d --build api frontend`; logar como `leandro`; aba 📅 Plano → "Gerar treinos diários até a prova" → ver a lista de dias e baixar um .zwo/.fit.

- [ ] **Step 5: Commit** — `git add frontend/app.py backend/app/api/routes/plans.py backend/app/schemas/training_plan.py && git commit -m "feat(frontend): generate + list daily workouts until race in Plano tab"`

---

## Self-Review (autor do plano)
- **Cobertura do spec:** geração por regra (Task 2 `allocate_days`); persistência idempotente + `source_plan_id` + migração (Tasks 1,3); endpoint (Task 3); export por dia (Task 4); frontend (Task 5); regras por bloco documentadas (Task 2 + Allocation rules); descanso por `weekly_days` (Task 3); FTP ausente → fallback 200 + estrutura %FTP (Task 3); tenant-scoping/isolamento testado (Tasks 3,4); prova no passado → 400 (Task 3).
- **Placeholders:** nenhum "TBD"; código completo. Pontos de "confirmar nome real" (TrainingWeek/encode_zwo) são verificações explícitas contra o código existente, não placeholders de lógica.
- **Consistência de tipos:** `WeekSpec`/`DailyPlanned`/`allocate_days` (Task 2) usados por `expand_plan_to_daily` (Task 3); `source_plan_id` (Task 1) usado em Tasks 3/4/5; `StructuredWorkout.model_dump/model_validate` ida-e-volta entre Task 3 (grava) e Task 4 (lê).
- **Risco conhecido:** distribuição de TSS é aproximada (dias de endurance escalados; dias de qualidade com TSS natural) — documentado; casamento exato do TSS semanal é out-of-scope v1.
