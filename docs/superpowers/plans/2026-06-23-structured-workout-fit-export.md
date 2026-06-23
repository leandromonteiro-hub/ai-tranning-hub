# Structured Workout `.fit` Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ao gerar uma recomendação diária, produzir um treino estruturado determinístico (intervalos em %FTP) e permitir que o atleta baixe um arquivo `.fit` workout para importar no ciclocomputador.

**Architecture:** Novo pacote `app/services/workout/` com três unidades isoladas — modelo canônico Pydantic (`model.py`), templates determinísticos guiados por `block_type`+`risk_level` (`templates.py` + `builder.py`), e encoder `.fit` via `fit-tool` (`fit_encoder.py`). O recomendador resolve FTP e bloco do dia, gera a estrutura e a serializa em `AiRecommendation.payload["structured_workout"]`. Um endpoint novo serve o `.fit` sob demanda. Sem tabela nova, sem migração.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Pydantic v2, `fit-tool` (encoding FIT), pytest/pytest-asyncio. Testes em SQLite (aiosqlite) dentro do container.

## Global Constraints

- **Isolamento multi-tenant na camada de repositório:** toda query athlete-scoped passa por `TenantRepository` (`app/repositories/base.py`), que adiciona `athlete_id == ctx.athlete_id` e `deleted_at IS NULL`. Nenhuma rota cruza tenants. (Regra inegociável do projeto.)
- **Guardrails antes de qualquer decisão:** a geração do treino estruturado usa o `risk_level` já calculado pelos guardrails; `risk_level=HIGH` SEMPRE resulta em treino de recuperação.
- **Só potência (%FTP)** nesta fatia. Sem FC, sem `.zwo`, sem calendário, sem push automático (YAGNI — fases futuras).
- **Comando de teste (container):** da raiz do repo, em Git Bash:
  `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <caminho> -v"`
  (paths de teste são relativos a `/app`, ex.: `app/tests/test_workout/test_model.py`).
- **FIT — fatos confirmados (round-trip validado):** `duration_value` em **milissegundos**; alvo custom de potência = **watts + 1000** (ex.: 225W → 1225); `Intensity` ACTIVE=0 / REST=1 / WARMUP=2 / COOLDOWN=3; `FileIdMessage` com `type=FileType.WORKOUT`, `manufacturer=Manufacturer.DEVELOPMENT.value`, **sem** `time_created`.
- **Encoder achata repetições** (expande `Repeat(count=n, steps=[...])` em `n` cópias sequenciais dos passos). Agrupamento nativo `repeat_until_steps_cmplt` fica para fase futura.
- **Commits frequentes**, um por tarefa concluída.

---

### Task 1: Modelo canônico do treino estruturado

**Files:**
- Create: `backend/app/services/workout/__init__.py` (vazio)
- Create: `backend/app/services/workout/model.py`
- Test: `backend/app/tests/test_workout/__init__.py` (vazio), `backend/app/tests/test_workout/test_model.py`

**Interfaces:**
- Produces: `Target`, `Step`, `Repeat`, `StructuredWorkout` (Pydantic). `StructuredWorkout(name: str, sport: str = "cycling", elements: list[Step | Repeat], estimated_tss: float | None = None, ftp_watts: float | None = None)`. `Step(intensity: Literal["warmup","active","rest","cooldown"], duration_s: int, target: Target, cadence_low: int | None, cadence_high: int | None, note: str | None)`. `Target(type: Literal["power_pct_ftp","open"], low: float | None, high: float | None)`. `Repeat(count: int, steps: list[Step])`.

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_workout/test_model.py
from app.services.workout.model import Target, Step, Repeat, StructuredWorkout


def test_structured_workout_roundtrips_through_json():
    w = StructuredWorkout(
        name="Sweet Spot",
        elements=[
            Step(intensity="warmup", duration_s=600,
                 target=Target(type="power_pct_ftp", low=0.55, high=0.65)),
            Repeat(count=3, steps=[
                Step(intensity="active", duration_s=720,
                     target=Target(type="power_pct_ftp", low=0.88, high=0.93)),
                Step(intensity="rest", duration_s=300,
                     target=Target(type="power_pct_ftp", low=0.50, high=0.55)),
            ]),
            Step(intensity="cooldown", duration_s=600,
                 target=Target(type="open", low=None, high=None)),
        ],
        ftp_watts=250.0,
    )
    dumped = w.model_dump(mode="json")
    restored = StructuredWorkout.model_validate(dumped)
    assert restored.name == "Sweet Spot"
    assert restored.ftp_watts == 250.0
    assert isinstance(restored.elements[1], Repeat)
    assert restored.elements[1].count == 3
    assert restored.elements[0].target.low == 0.55
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_workout/test_model.py -v"`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.workout'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/workout/model.py
"""Canonical, format-agnostic structured workout model.

Targets are expressed as fractions of FTP (e.g. 0.90 == 90% FTP). The absolute
FTP used at generation time is carried in ``ftp_watts`` so any exporter can
resolve watts without re-querying. This is the reusable core for future
exporters (.zwo, etc.) and the day-by-day calendar.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Target(BaseModel):
    type: Literal["power_pct_ftp", "open"]
    low: float | None = None   # fraction of FTP, e.g. 0.88
    high: float | None = None


class Step(BaseModel):
    intensity: Literal["warmup", "active", "rest", "cooldown"]
    duration_s: int
    target: Target
    cadence_low: int | None = None
    cadence_high: int | None = None
    note: str | None = None


class Repeat(BaseModel):
    count: int
    steps: list[Step]


class StructuredWorkout(BaseModel):
    name: str
    sport: Literal["cycling"] = "cycling"
    elements: list[Step | Repeat]
    estimated_tss: float | None = None
    ftp_watts: float | None = None
```

Also create empty `backend/app/services/workout/__init__.py` and `backend/app/tests/test_workout/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_workout/test_model.py -v"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/workout/__init__.py backend/app/services/workout/model.py backend/app/tests/test_workout/
git commit -m "feat(workout): canonical structured workout model"
```

---

### Task 2: Templates determinísticos + builder

**Files:**
- Create: `backend/app/services/workout/templates.py`
- Create: `backend/app/services/workout/builder.py`
- Test: `backend/app/tests/test_workout/test_builder.py`

**Interfaces:**
- Consumes: `Target, Step, Repeat, StructuredWorkout` (Task 1); `BlockType, RiskLevel` (`app/models/enums.py`).
- Produces: `templates.TEMPLATES: dict[BlockType, Callable[[float], StructuredWorkout]]`; `templates.recovery(ftp_watts: float) -> StructuredWorkout`; `builder.build_for(block_type: BlockType, risk_level: RiskLevel, ftp_watts: float) -> StructuredWorkout`.

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_workout/test_builder.py
import pytest

from app.models.enums import BlockType, RiskLevel
from app.services.workout.builder import build_for
from app.services.workout.model import Repeat


def _all_active_targets(w):
    out = []
    for el in w.elements:
        steps = el.steps if isinstance(el, Repeat) else [el]
        for s in steps:
            if s.intensity == "active" and s.target.low is not None:
                out.append(s.target.low)
    return out


def test_high_risk_always_recovery_regardless_of_block():
    for block in BlockType:
        w = build_for(block, RiskLevel.HIGH, 250.0)
        assert "recup" in w.name.lower() or "recovery" in w.name.lower()
        # recovery is easy: no active interval above 0.75 FTP
        assert all(t <= 0.75 for t in _all_active_targets(w))


def test_build_sets_ftp_and_low_risk_build_is_sweet_spot():
    w = build_for(BlockType.BUILD, RiskLevel.LOW, 250.0)
    assert w.ftp_watts == 250.0
    # sweet spot has a repeated active block around 0.88-0.93 FTP
    reps = [e for e in w.elements if isinstance(e, Repeat)]
    assert reps and reps[0].count == 3
    assert any(0.85 <= t <= 0.95 for t in _all_active_targets(w))


def test_moderate_reduces_volume_without_raising_intensity():
    low = build_for(BlockType.BUILD, RiskLevel.LOW, 250.0)
    mod = build_for(BlockType.BUILD, RiskLevel.MODERATE, 250.0)
    low_reps = [e for e in low.elements if isinstance(e, Repeat)][0].count
    mod_reps = [e for e in mod.elements if isinstance(e, Repeat)][0].count
    assert mod_reps < low_reps
    # intensity (peak active target) never exceeds the LOW version
    assert max(_all_active_targets(mod)) <= max(_all_active_targets(low))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_workout/test_builder.py -v"`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.workout.builder'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/workout/templates.py
"""Deterministic workout templates, parameterised by FTP.

Each template returns a StructuredWorkout with targets as fractions of FTP.
Zone anchors follow docs/training_methodology.md (Z1 recovery ~0.50-0.58,
Z2 endurance ~0.62-0.68, sweet spot ~0.88-0.93, VO2max ~1.10-1.18).
"""
from __future__ import annotations

from typing import Callable

from app.models.enums import BlockType
from app.services.workout.model import Repeat, Step, StructuredWorkout, Target


def _pwr(low: float, high: float) -> Target:
    return Target(type="power_pct_ftp", low=low, high=high)


def _open() -> Target:
    return Target(type="open")


def recovery(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Recuperação Z1",
        elements=[Step(intensity="active", duration_s=2700, target=_pwr(0.50, 0.58))],
    )


def endurance(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Endurance Z2",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.60)),
            Step(intensity="active", duration_s=3600, target=_pwr(0.62, 0.68)),
            Step(intensity="cooldown", duration_s=600, target=_open()),
        ],
    )


def sweet_spot(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Sweet Spot 3x12",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.65)),
            Repeat(count=3, steps=[
                Step(intensity="active", duration_s=720, target=_pwr(0.88, 0.93)),
                Step(intensity="rest", duration_s=300, target=_pwr(0.50, 0.55)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=_open()),
        ],
    )


def vo2max(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="VO2max 5x4",
        elements=[
            Step(intensity="warmup", duration_s=900, target=_pwr(0.55, 0.70)),
            Repeat(count=5, steps=[
                Step(intensity="active", duration_s=240, target=_pwr(1.10, 1.18)),
                Step(intensity="rest", duration_s=240, target=_pwr(0.45, 0.50)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=_open()),
        ],
    )


def openers(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Openers 3x1",
        elements=[
            Step(intensity="warmup", duration_s=900, target=_pwr(0.55, 0.65)),
            Repeat(count=3, steps=[
                Step(intensity="active", duration_s=60, target=_pwr(1.05, 1.15)),
                Step(intensity="rest", duration_s=180, target=_pwr(0.50, 0.55)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=_open()),
        ],
    )


TEMPLATES: dict[BlockType, Callable[[float], StructuredWorkout]] = {
    BlockType.BASE: endurance,
    BlockType.BUILD: sweet_spot,
    BlockType.PEAK: vo2max,
    BlockType.TAPER: openers,
    BlockType.RECOVERY: recovery,
}
```

```python
# backend/app/services/workout/builder.py
"""Select and build a structured workout from the day's training intent.

The intent is the SAME (block_type, risk_level) the guardrails already produce,
so the structured workout inherits the safety posture: HIGH risk -> recovery,
MODERATE -> the block template with reduced volume (never higher intensity).
"""
from __future__ import annotations

from app.models.enums import BlockType, RiskLevel
from app.services.workout import templates
from app.services.workout.model import Repeat, StructuredWorkout


def _reduce(workout: StructuredWorkout) -> StructuredWorkout:
    """MODERATE risk: drop one repetition from each repeated block (min 1)."""
    new_elements = []
    for el in workout.elements:
        if isinstance(el, Repeat):
            new_elements.append(Repeat(count=max(1, el.count - 1), steps=el.steps))
        else:
            new_elements.append(el)
    return StructuredWorkout(
        name=workout.name + " (reduzido)",
        sport=workout.sport,
        elements=new_elements,
        ftp_watts=workout.ftp_watts,
    )


def build_for(
    block_type: BlockType, risk_level: RiskLevel, ftp_watts: float
) -> StructuredWorkout:
    if risk_level == RiskLevel.HIGH:
        workout = templates.recovery(ftp_watts)
    else:
        template_fn = templates.TEMPLATES.get(block_type, templates.endurance)
        workout = template_fn(ftp_watts)
        if risk_level == RiskLevel.MODERATE:
            workout = _reduce(workout)
    workout.ftp_watts = ftp_watts
    return workout
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_workout/test_builder.py -v"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/workout/templates.py backend/app/services/workout/builder.py backend/app/tests/test_workout/test_builder.py
git commit -m "feat(workout): deterministic templates + guardrail-aware builder"
```

---

### Task 3: Encoder `.fit` (+ dependência `fit-tool`)

**Files:**
- Modify: `backend/pyproject.toml` (adicionar `fit-tool` às dependências principais)
- Create: `backend/app/services/workout/fit_encoder.py`
- Test: `backend/app/tests/test_workout/test_fit_encoder.py`

**Interfaces:**
- Consumes: `StructuredWorkout, Step, Repeat` (Task 1).
- Produces: `fit_encoder.encode(workout: StructuredWorkout) -> bytes`. Requer `workout.ftp_watts` (levanta `ValueError` se ausente). Achata repetições.

- [ ] **Step 1: Add the dependency**

Em `backend/pyproject.toml`, na lista `dependencies = [...]`, adicionar a linha (após `"httpx>=0.28",`):

```toml
    "fit-tool>=0.9",
```

- [ ] **Step 2: Write the failing test**

```python
# backend/app/tests/test_workout/test_fit_encoder.py
import pytest

from app.services.workout.fit_encoder import encode
from app.services.workout.model import Repeat, Step, StructuredWorkout, Target


def _decode_steps(data: bytes):
    from fit_tool.fit_file import FitFile
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    steps = []
    for r in FitFile.from_bytes(data).records:
        if isinstance(r.message, WorkoutStepMessage):
            m = r.message
            steps.append((m.intensity, m.duration_value,
                          m.custom_target_power_low, m.custom_target_power_high))
    return steps


def test_encode_flattens_repeats_and_encodes_watts():
    w = StructuredWorkout(
        name="Sweet Spot 3x12",
        elements=[
            Step(intensity="warmup", duration_s=600,
                 target=Target(type="power_pct_ftp", low=0.55, high=0.65)),
            Repeat(count=3, steps=[
                Step(intensity="active", duration_s=720,
                     target=Target(type="power_pct_ftp", low=0.88, high=0.93)),
                Step(intensity="rest", duration_s=300,
                     target=Target(type="power_pct_ftp", low=0.50, high=0.55)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=Target(type="open")),
        ],
        ftp_watts=250.0,
    )
    data = encode(w)
    steps = _decode_steps(data)
    # 1 warmup + (2 steps * 3) + 1 cooldown = 8 flattened steps
    assert len(steps) == 8
    # warmup duration is in ms
    assert steps[0][1] == 600000
    # first active interval: 0.88*250=220W -> 1220, 0.93*250=232.5->round 233 -> 1233
    assert steps[1][0] == 0      # Intensity.ACTIVE == 0
    assert steps[1][2] == 1220
    assert steps[1][3] == 1233


def test_encode_requires_ftp():
    w = StructuredWorkout(name="x", elements=[
        Step(intensity="active", duration_s=600, target=Target(type="open"))])
    with pytest.raises(ValueError):
        encode(w)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_workout/test_fit_encoder.py -v"`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.workout.fit_encoder'` (a dependência `fit-tool` é instalada pelo `pip install -e '.[dev]'` por já estar em `dependencies`).

- [ ] **Step 4: Write minimal implementation**

```python
# backend/app/services/workout/fit_encoder.py
"""Encode a StructuredWorkout as a Garmin FIT workout file (power targets).

Repeats are flattened into sequential steps (robust thin-slice choice; native
repeat_until_steps_cmplt grouping is a future enhancement). FIT conventions
(validated by round-trip): duration in ms; custom power target = watts + 1000.
"""
from __future__ import annotations

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.workout_message import WorkoutMessage
from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
from fit_tool.profile.profile_type import (
    FileType, Intensity, Manufacturer, Sport, WorkoutStepDuration, WorkoutStepTarget,
)

from app.services.workout.model import Repeat, Step, StructuredWorkout

_INTENSITY = {
    "warmup": Intensity.WARMUP,
    "active": Intensity.ACTIVE,
    "rest": Intensity.REST,
    "cooldown": Intensity.COOLDOWN,
}


def _flatten(elements: list) -> list[Step]:
    out: list[Step] = []
    for el in elements:
        if isinstance(el, Repeat):
            for _ in range(el.count):
                out.extend(el.steps)
        else:
            out.append(el)
    return out


def _power_field(frac: float, ftp_watts: float) -> int:
    return round(frac * ftp_watts) + 1000


def encode(workout: StructuredWorkout) -> bytes:
    if not workout.ftp_watts:
        raise ValueError("workout.ftp_watts is required to encode power targets")
    ftp = workout.ftp_watts
    steps = _flatten(workout.elements)

    builder = FitFileBuilder(auto_define=True)

    fid = FileIdMessage()
    fid.type = FileType.WORKOUT
    fid.manufacturer = Manufacturer.DEVELOPMENT.value
    fid.product = 0
    fid.serial_number = 1
    builder.add(fid)

    wm = WorkoutMessage()
    wm.workout_name = workout.name
    wm.sport = Sport.CYCLING
    wm.num_valid_steps = len(steps)
    builder.add(wm)

    for i, st in enumerate(steps):
        m = WorkoutStepMessage()
        m.message_index = i
        m.intensity = _INTENSITY[st.intensity]
        m.duration_type = WorkoutStepDuration.TIME
        m.duration_value = st.duration_s * 1000
        if st.target.type == "power_pct_ftp" and st.target.low is not None:
            high = st.target.high if st.target.high is not None else st.target.low
            m.target_type = WorkoutStepTarget.POWER
            m.custom_target_power_low = _power_field(st.target.low, ftp)
            m.custom_target_power_high = _power_field(high, ftp)
        else:
            m.target_type = WorkoutStepTarget.OPEN
        builder.add(m)

    return builder.build().to_bytes()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_workout/test_fit_encoder.py -v"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app/services/workout/fit_encoder.py backend/app/tests/test_workout/test_fit_encoder.py
git commit -m "feat(workout): FIT workout encoder (power targets, flattened repeats)"
```

---

### Task 4: Repositório do bloco do dia (`TrainingWeekRepository.block_on`)

**Files:**
- Create: `backend/app/repositories/plan_repo.py`
- Test: `backend/app/tests/test_planning/test_block_lookup.py`

**Interfaces:**
- Consumes: `TenantRepository` (`app/repositories/base.py`), `TrainingWeek` (`app/models/training_plan.py`), `BlockType` (`app/models/enums.py`). Test fixtures: `session`, `two_athletes`, `ctx_for` (`app/tests/conftest.py`).
- Produces: `TrainingWeekRepository(session, ctx)` com `async block_on(d: date, athlete_id: uuid.UUID | None = None) -> BlockType | None` — retorna o `block_type` da semana que cobre `d` (`week_start <= d < week_start + 7 dias`), ou `None` se não houver.

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_planning/test_block_lookup.py
from datetime import date, timedelta

import pytest

from app.models.enums import BlockType
from app.models.training_plan import TrainingPlan, TrainingWeek
from app.repositories.plan_repo import TrainingWeekRepository
from app.tests.conftest import ctx_for

pytestmark = pytest.mark.asyncio


async def test_block_on_returns_block_for_covering_week(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    plan = TrainingPlan(athlete_id=a.id, created_by=a.id, name="P",
                        start_date=date(2026, 6, 1), total_weeks=1)
    session.add(plan)
    await session.flush()
    monday = date(2026, 6, 1)
    session.add(TrainingWeek(athlete_id=a.id, created_by=a.id, plan_id=plan.id,
                             week_index=1, week_start=monday,
                             block_type=BlockType.BUILD, planned_tss=300.0))
    await session.flush()

    repo = TrainingWeekRepository(session, ctx)
    assert await repo.block_on(monday + timedelta(days=3)) == BlockType.BUILD
    # a date past the week window has no covering week
    assert await repo.block_on(monday + timedelta(days=9)) is None
    # a date before any week
    assert await repo.block_on(monday - timedelta(days=1)) is None


async def test_block_on_is_tenant_isolated(session, two_athletes):
    a, b = two_athletes
    plan = TrainingPlan(athlete_id=a.id, created_by=a.id, name="P",
                        start_date=date(2026, 6, 1), total_weeks=1)
    session.add(plan)
    await session.flush()
    session.add(TrainingWeek(athlete_id=a.id, created_by=a.id, plan_id=plan.id,
                             week_index=1, week_start=date(2026, 6, 1),
                             block_type=BlockType.PEAK, planned_tss=300.0))
    await session.flush()

    # Athlete B must not see athlete A's training week.
    repo_b = TrainingWeekRepository(session, ctx_for(b))
    assert await repo_b.block_on(date(2026, 6, 3)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_planning/test_block_lookup.py -v"`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.repositories.plan_repo'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/repositories/plan_repo.py
"""Repository for training-plan reads (tenant-isolated)."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.models.enums import BlockType
from app.models.training_plan import TrainingWeek
from app.repositories.base import TenantRepository


class TrainingWeekRepository(TenantRepository[TrainingWeek]):
    model = TrainingWeek

    async def block_on(
        self, d: date, athlete_id: uuid.UUID | None = None
    ) -> BlockType | None:
        """Block type of the plan week covering date ``d``, else None."""
        stmt = (
            self._base_select(athlete_id)
            .where(TrainingWeek.week_start <= d)
            .order_by(TrainingWeek.week_start.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        week = res.scalar_one_or_none()
        if week and (d - week.week_start) < timedelta(days=7):
            return week.block_type
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_planning/test_block_lookup.py -v"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/plan_repo.py backend/app/tests/test_planning/test_block_lookup.py
git commit -m "feat(planning): tenant-isolated block-of-day lookup"
```

---

### Task 5: Integrar a geração do treino estruturado no recomendador

**Files:**
- Modify: `backend/app/services/ai/recommender.py`
- Test: `backend/app/tests/test_workout/test_recommender_structured.py`

**Interfaces:**
- Consumes: `build_for` (Task 2), `FtpRepository.value_on` (`app/repositories/metrics_repo.py`), `TrainingWeekRepository.block_on` (Task 4), `BlockType` (`app/models/enums.py`). Existing `generate_recommendation(session, ctx, athlete_id, *, target_date, kind, question)`.
- Produces: após gerar, `recommendation.payload["structured_workout"]` contém o dump JSON de um `StructuredWorkout` quando o atleta tem FTP vigente; `None` caso contrário. Comportamento existente (risco, evidência, LLM) inalterado.

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_workout/test_recommender_structured.py
from datetime import date

import pytest

from app.models.metrics import FtpHistory
from app.services.ai.recommender import generate_recommendation
from app.tests.conftest import ctx_for

pytestmark = pytest.mark.asyncio


async def test_recommendation_includes_structured_workout_when_ftp_present(
    session, two_athletes
):
    a, _ = two_athletes
    ctx = ctx_for(a)
    session.add(FtpHistory(athlete_id=a.id, created_by=a.id,
                           ftp_watts=240.0, valid_from=date(2026, 1, 1)))
    await session.flush()

    rec = await generate_recommendation(
        session, ctx, a.id, target_date=date(2026, 6, 23), kind="daily_workout"
    )
    sw = rec.payload.get("structured_workout")
    assert sw is not None
    assert sw["ftp_watts"] == 240.0
    assert len(sw["elements"]) >= 1


async def test_recommendation_has_no_structured_workout_without_ftp(
    session, two_athletes
):
    a, _ = two_athletes
    rec = await generate_recommendation(
        session, ctx_for(a), a.id, target_date=date(2026, 6, 23), kind="daily_workout"
    )
    assert (rec.payload or {}).get("structured_workout") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_workout/test_recommender_structured.py -v"`
Expected: FAIL — `assert sw is not None` falha (payload ainda não tem `structured_workout`).

- [ ] **Step 3: Write minimal implementation**

Em `backend/app/services/ai/recommender.py`, adicionar aos imports (junto aos outros `from app...`):

```python
from app.models.enums import BlockType
from app.repositories.metrics_repo import FtpRepository
from app.repositories.plan_repo import TrainingWeekRepository
from app.services.workout.builder import build_for
```

Depois do bloco de guardrails (logo após `log.info("guardrails_evaluated", ...)`), inserir:

```python
    # Structured workout (deterministic, inherits the guardrail risk posture).
    ftp_watts = await FtpRepository(session, ctx).value_on(target_date, athlete_id)
    structured_workout = None
    if ftp_watts:
        block = (
            await TrainingWeekRepository(session, ctx).block_on(target_date, athlete_id)
            or BlockType.BASE
        )
        structured_workout = build_for(
            block, safety.risk_level, ftp_watts
        ).model_dump(mode="json")
```

Na construção do `AiRecommendation(...)`, substituir o `payload`:

```python
        payload={"llm_text": llm.text, "template_version": template_version},
```

por:

```python
        payload={
            "llm_text": llm.text,
            "template_version": template_version,
            "structured_workout": structured_workout,
        },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_workout/test_recommender_structured.py -v"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/recommender.py backend/app/tests/test_workout/test_recommender_structured.py
git commit -m "feat(ai): attach deterministic structured workout to recommendations"
```

---

### Task 6: Endpoint de download `.fit`

**Files:**
- Modify: `backend/app/api/routes/recommendations.py`
- Test: `backend/app/tests/test_api/test_workout_export.py`

**Interfaces:**
- Consumes: `RecommendationRepository.get` (`app/repositories/ai_repo.py`), `fit_encoder.encode` (Task 3), `StructuredWorkout.model_validate` (Task 1), `get_tenant`/`get_db` deps. FastAPI `Response`.
- Produces: `GET /api/v1/recommendations/{rec_id}/export.fit` → 200 com bytes `.fit` (`application/octet-stream`) para o dono; 404 se a recomendação não existir, for de outro tenant, ou não tiver `structured_workout`.

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_api/test_workout_export.py
from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role
from app.models.metrics import FtpHistory

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client_with_ftp():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        a = Athlete(email="a@example.com", hashed_password=hash_password("pw12345678"),
                    full_name="A", role=Role.ATHLETE, tenant_id="ta")
        b = Athlete(email="b@example.com", hashed_password=hash_password("pw12345678"),
                    full_name="B", role=Role.ATHLETE, tenant_id="tb")
        s.add_all([a, b])
        await s.flush()
        s.add(FtpHistory(athlete_id=a.id, created_by=a.id,
                         ftp_watts=250.0, valid_from=date(2026, 1, 1)))
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
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def _login(client, email):
    r = await client.post("/api/v1/auth/login",
                          data={"username": email, "password": "pw12345678"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def test_export_fit_returns_file_for_owner_and_isolates_others(client_with_ftp):
    ha = {"Authorization": f"Bearer {await _login(client_with_ftp, 'a@example.com')}"}
    hb = {"Authorization": f"Bearer {await _login(client_with_ftp, 'b@example.com')}"}

    rec = await client_with_ftp.post("/api/v1/recommendations", headers=ha,
                                     json={"kind": "daily_workout"})
    assert rec.status_code == 201, rec.text
    rec_id = rec.json()["id"]

    ok = await client_with_ftp.get(f"/api/v1/recommendations/{rec_id}/export.fit", headers=ha)
    assert ok.status_code == 200, ok.text
    assert ok.headers["content-type"] == "application/octet-stream"
    assert ok.content[8:12] == b".FIT"  # FIT header magic

    cross = await client_with_ftp.get(f"/api/v1/recommendations/{rec_id}/export.fit", headers=hb)
    assert cross.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_workout_export.py -v"`
Expected: FAIL — endpoint inexistente retorna 404 para o dono (`assert ok.status_code == 200` falha).

- [ ] **Step 3: Write minimal implementation**

Em `backend/app/api/routes/recommendations.py`, adicionar aos imports:

```python
from fastapi import Response
from app.services.workout.fit_encoder import encode as encode_fit
from app.services.workout.model import StructuredWorkout
```

E adicionar a rota (após `get_recommendation`):

```python
@router.get("/{rec_id}/export.fit")
async def export_recommendation_fit(
    rec_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Download the recommendation's structured workout as a Garmin FIT file."""
    repo = RecommendationRepository(db, ctx)
    rec = await repo.get(rec_id)
    sw_data = (rec.payload or {}).get("structured_workout") if rec else None
    if not sw_data:
        raise HTTPException(status_code=404, detail="No structured workout for this recommendation")
    workout = StructuredWorkout.model_validate(sw_data)
    data = encode_fit(workout)
    slug = "".join(c if c.isalnum() else "_" for c in workout.name).strip("_") or "workout"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{slug}.fit"'},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_workout_export.py -v"`
Expected: PASS

- [ ] **Step 5: Run the FULL suite to confirm no regressions**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest -q"`
Expected: PASS (todos os testes anteriores + os novos).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/recommendations.py backend/app/tests/test_api/test_workout_export.py
git commit -m "feat(api): GET /recommendations/{id}/export.fit download endpoint"
```

---

### Task 7: Botão de download no frontend Streamlit

**Files:**
- Modify: `frontend/app.py`

**Interfaces:**
- Consumes: endpoint `GET /recommendations/{id}/export.fit` (Task 6); `rec["payload"]["structured_workout"]` (exposto via `RecommendationRead.payload`). Helper `api(...)` existente.
- Produces: na aba "🧠 Recomendações", um `st.download_button` com os bytes do `.fit`, exibido apenas quando há treino estruturado. Sem teste automatizado (UI Streamlit); validado manualmente.

- [ ] **Step 1: Add the download button**

Em `frontend/app.py`, dentro de `with tab_rec:`, no bloco `if rec:`, logo após o `with st.expander("Justificativa, evidências e ajustes"):` (antes do `st.divider()` do feedback), inserir:

```python
            has_structured = bool((rec.get("payload") or {}).get("structured_workout"))
            if has_structured:
                fit_resp = api("GET", f"/recommendations/{rec['id']}/export.fit", token=token)
                if fit_resp.status_code == 200:
                    st.download_button(
                        "⬇️ Baixar treino (.fit)",
                        data=fit_resp.content,
                        file_name=f"treino_{rec['id'][:8]}.fit",
                        mime="application/octet-stream",
                    )
```

- [ ] **Step 2: Manual verification (frontend up)**

Run (stack já no ar): abrir http://localhost:8501, logar como `athlete1@athletehub.example.com`, gerar uma recomendação e confirmar que o botão "⬇️ Baixar treino (.fit)" aparece e baixa um arquivo `.fit` não-vazio.
Expected: arquivo `.fit` baixado (> 0 bytes).

- [ ] **Step 3: Commit**

```bash
git add frontend/app.py
git commit -m "feat(frontend): download structured workout as .fit on recommendation"
```

---

## Gate de aceitação manual (não-código)

Após as 7 tarefas e suíte verde, **antes de considerar a hipótese provada**:

- [ ] Confirmar o modelo do ciclocomputador de pelo menos um dos 2 atletas.
- [ ] Gerar um `.fit` real, importá-lo no device (sideload USB para a pasta `NewFiles/` de um Garmin Edge, ou via Garmin Connect) e confirmar que o treino estruturado aparece e executa com os alvos de potência corretos.

Sem este passo, apenas a metade backend da hipótese está provada.

---

## Self-Review (preenchido pelo autor do plano)

- **Cobertura do spec:** §3 modelo → Task 1; §4 templates+seleção → Task 2; §5 encoder `.fit` → Task 3; resolução de bloco (isolada) → Task 4; integração no recomendador + `payload` → Task 5; §6 endpoint → Task 6; §6 frontend → Task 7; §8 gate no device → seção de aceitação manual. Decisão de achatar repetições e a dependência `fit-tool` (principal) documentadas em Global Constraints / Task 3.
- **Placeholders:** nenhum; todo passo de código traz o código completo e comandos exatos.
- **Consistência de tipos:** `StructuredWorkout`/`Step`/`Repeat`/`Target` (Task 1) usados igualmente em Tasks 2/3/5/6; `build_for(block_type, risk_level, ftp_watts)` (Task 2) chamado em Task 5; `encode(workout)` (Task 3) chamado em Task 6; `block_on(d, athlete_id=None)` (Task 4) chamado em Task 5; `ftp_watts` é campo do modelo e parâmetro coerentes.
