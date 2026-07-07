# Recomendação comparativa Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Em cada recomendação diária, gerar também o treino que o "método tradicional" do atleta (twin do histórico) prescreveria, mostrar os dois lado a lado, e deixar o atleta escolher qual vira o treino do dia (calendário/Garmin).

**Architecture:** Um novo builder determinístico transforma o `intensity_split`/bloco/duração-típica do twin num `StructuredWorkout`. O recommender guarda os dois treinos no `payload` (jsonb, sem migração) e o prompt passa a contrastá-los. O export e o aceite ganham uma `variant` (`ai`|`methodology`); o push ao Garmin usa a variante escolhida. O frontend mostra dois cards com botão "Usar este".

**Tech Stack:** FastAPI + SQLAlchemy async + pytest (via Docker); Next.js 15 + SWR + vitest.

**Spec:** `docs/superpowers/specs/2026-07-07-recomendacao-comparativa-design.md`

## Global Constraints

- Testes backend SÓ via Docker: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest <PATH> -q --no-header -p no:warnings"`
- Testes web no host: `cd web && npx vitest run <PATH>`.
- Branch: `feat/recomendacao-comparativa` (já existe, spec commitada).
- Commits terminam com `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Fallback de duração por bloco (verbatim): BASE 5400s, BUILD 4500s, PEAK 3600s, TAPER 2700s, RECOVERY 2700s.
- Chaves novas no payload (verbatim): `methodology_workout`, `methodology_workout_description`.
- `variant` (verbatim): `"ai"` (default, comportamento atual) | `"methodology"`.
- Primitivos reusados: `StructuredWorkout`/`Step`/`Repeat`/`Target` de `app/services/workout/model.py`; `analysis.estimated_tss`/`analysis.describe`; `build_for` de `app/services/workout/builder.py` (fallback genérico).

---

### Task 1: Builder do método tradicional (`methodology_builder.py`)

**Files:**
- Create: `backend/app/services/workout/methodology_builder.py`
- Test: `backend/app/tests/test_workout/test_methodology_builder.py`

**Interfaces:**
- Consumes: `StructuredWorkout`/`Step`/`Repeat`/`Target`; `analysis.estimated_tss`; `build_for` (fallback); `BlockType`/`RiskLevel`.
- Produces:
  - `typical_duration_for(durations_s: list[int], block_type: BlockType) -> int` — mediana das durações; fallback por bloco quando `len < 3`.
  - `build_methodology_workout(intensity_split: dict | None, block_type: BlockType, ftp_watts: float, typical_duration_s: int, risk_level: RiskLevel) -> StructuredWorkout`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/app/tests/test_workout/test_methodology_builder.py`:

```python
"""Builder do 'método tradicional': treino no estilo histórico do atleta."""
from __future__ import annotations

from app.models.enums import BlockType, RiskLevel
from app.services.workout import analysis
from app.services.workout.methodology_builder import (
    build_methodology_workout,
    typical_duration_for,
)
from app.services.workout.model import Repeat


def _total_s(w) -> int:
    return analysis.total_duration_s(w)


def test_typical_duration_median_when_enough_history():
    assert typical_duration_for([3600, 5400, 7200], BlockType.BASE) == 5400


def test_typical_duration_fallback_per_block_when_sparse():
    assert typical_duration_for([], BlockType.BASE) == 5400
    assert typical_duration_for([3600], BlockType.PEAK) == 3600  # <3 amostras


def test_pyramidal_base_is_endurance_scaled_to_typical():
    split = {"z1_pct": 0.68, "z2_pct": 0.29, "z3_pct": 0.03}
    w = build_methodology_workout(split, BlockType.BASE, 250.0, 5400, RiskLevel.LOW)
    # Endurance (sem repeats de intensidade) e duração ~= típica.
    assert not any(isinstance(el, Repeat) for el in w.elements)
    assert abs(_total_s(w) - 5400) <= 60
    assert "seu padrão" in w.name.lower()
    assert w.estimated_tss and w.estimated_tss > 0


def test_threshold_history_build_has_intervals():
    split = {"z1_pct": 0.55, "z2_pct": 0.25, "z3_pct": 0.20}
    w = build_methodology_workout(split, BlockType.BUILD, 250.0, 4500, RiskLevel.LOW)
    assert any(isinstance(el, Repeat) for el in w.elements)


def test_high_risk_forces_recovery():
    split = {"z1_pct": 0.55, "z2_pct": 0.25, "z3_pct": 0.20}
    w = build_methodology_workout(split, BlockType.BUILD, 250.0, 4500, RiskLevel.HIGH)
    assert "recupera" in w.name.lower()


def test_missing_split_falls_back_to_generic_block_template():
    w = build_methodology_workout(None, BlockType.BASE, 250.0, 5400, RiskLevel.LOW)
    # Cai no build_for (genérico) — nome do template padrão, não "seu padrão".
    assert "seu padrão" not in w.name.lower()
    assert w.estimated_tss and w.estimated_tss > 0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_workout/test_methodology_builder.py -q --no-header -p no:warnings"`
Expected: FAIL — `ModuleNotFoundError: methodology_builder`

- [ ] **Step 3: Implementar**

Criar `backend/app/services/workout/methodology_builder.py`:

```python
"""Builder do treino que o MÉTODO TRADICIONAL do atleta (twin do histórico)
prescreveria hoje. Determinístico e puro: distribuição de intensidade + bloco +
duração típica -> StructuredWorkout no estilo do atleta. Sem histórico/dados
ralos, cai no template genérico do bloco (build_for)."""
from __future__ import annotations

from statistics import median

from app.models.enums import BlockType, RiskLevel
from app.services.workout import analysis
from app.services.workout.builder import build_for
from app.services.workout.model import Repeat, Step, StructuredWorkout, Target

# Fallback de duração por bloco (segundos) quando o histórico é ralo.
_FALLBACK_DURATION_S: dict[BlockType, int] = {
    BlockType.BASE: 5400,
    BlockType.BUILD: 4500,
    BlockType.PEAK: 3600,
    BlockType.TAPER: 2700,
    BlockType.RECOVERY: 2700,
}
# Acima deste share de Z3 histórico consideramos que o atleta faz intensidade.
_Z3_INTERVAL_THRESHOLD = 0.15
_MIN_HISTORY = 3  # amostras mínimas para usar a mediana em vez do fallback


def typical_duration_for(durations_s: list[int], block_type: BlockType) -> int:
    usable = [d for d in durations_s if d and d > 0]
    if len(usable) >= _MIN_HISTORY:
        return int(median(usable))
    return _FALLBACK_DURATION_S.get(block_type, 5400)


def _pwr(low: float, high: float) -> Target:
    return Target(type="power_pct_ftp", low=low, high=high)


def _endurance(typical_s: int) -> list[Step | Repeat]:
    """Z2 do tamanho típico: 10min aquece, bloco Z2, 10min desaquece."""
    main = max(600, typical_s - 1200)
    return [
        Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.60)),
        Step(intensity="active", duration_s=main, target=_pwr(0.62, 0.68)),
        Step(intensity="cooldown", duration_s=600, target=_pwr(0.40, 0.50)),
    ]


def _intervals(typical_s: int, work_s: int, rest_s: int, low: float, high: float) -> list[Step | Repeat]:
    """Sessão de intervalos ajustando o nº de reps p/ caber na duração típica."""
    budget = max(0, typical_s - 1200)  # tira aquecimento + desaquecimento
    reps = max(2, min(6, budget // (work_s + rest_s)))
    return [
        Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.65)),
        Repeat(count=int(reps), steps=[
            Step(intensity="active", duration_s=work_s, target=_pwr(low, high)),
            Step(intensity="rest", duration_s=rest_s, target=_pwr(0.50, 0.55)),
        ]),
        Step(intensity="cooldown", duration_s=600, target=_pwr(0.40, 0.50)),
    ]


def build_methodology_workout(
    intensity_split: dict | None,
    block_type: BlockType,
    ftp_watts: float,
    typical_duration_s: int,
    risk_level: RiskLevel,
) -> StructuredWorkout:
    # Mesmo guardrail do build_for: HIGH risk -> recuperação.
    if risk_level == RiskLevel.HIGH:
        w = build_for(block_type, RiskLevel.HIGH, ftp_watts)
        w.name = "Recuperação Z1 (seu padrão)"
        return w

    z3 = (intensity_split or {}).get("z3_pct")
    if not intensity_split or z3 is None:
        # Sem histórico suficiente -> template genérico do bloco (honesto).
        return build_for(block_type, risk_level, ftp_watts)

    does_intensity = float(z3) >= _Z3_INTERVAL_THRESHOLD
    if does_intensity and block_type in (BlockType.BUILD, BlockType.PEAK):
        if block_type == BlockType.PEAK:
            elements = _intervals(typical_duration_s, 240, 240, 1.10, 1.18)
            name = "VO2max (seu padrão)"
        else:
            elements = _intervals(typical_duration_s, 720, 300, 0.88, 0.93)
            name = "Sweet Spot (seu padrão)"
    else:
        # Pirâmidal / pouco Z3 / blocos de base -> pão-com-manteiga Z2.
        elements = _endurance(typical_duration_s)
        name = "Endurance Z2 (seu padrão)"

    workout = StructuredWorkout(name=name, elements=elements, ftp_watts=ftp_watts)
    workout.estimated_tss = analysis.estimated_tss(workout)
    return workout
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_workout/test_methodology_builder.py -q --no-header -p no:warnings; ruff check app/services/workout/methodology_builder.py app/tests/test_workout/test_methodology_builder.py"`
Expected: verde + `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/workout/methodology_builder.py backend/app/tests/test_workout/test_methodology_builder.py
git commit -m "feat(recs): builder do treino do método tradicional (twin -> StructuredWorkout)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Wiring no recommender + prompt contrastivo

**Files:**
- Modify: `backend/app/services/ai/recommender.py` (`generate_recommendation`)
- Modify: `backend/app/services/ai/prompts.py` (template + versão + render)
- Test: `backend/app/tests/test_ai/test_comparative_payload.py`

**Interfaces:**
- Consumes: `build_methodology_workout`, `typical_duration_for` (Task 1); `workout_analysis.describe`.
- Produces: `payload["methodology_workout"]` (dict do StructuredWorkout) e `payload["methodology_workout_description"]` (str) presentes quando há `ftp_watts` e `twin_seed.intensity_split`; ausentes quando não há FTP. Template `daily_workout` sobe para versão 5 e recebe a var `{methodology_workout}`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `backend/app/tests/test_ai/test_comparative_payload.py`:

```python
"""generate_recommendation carrega os DOIS treinos no payload (comparativa)."""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.enums import BlockType
from app.services.ai import recommender
from app.services.ai.recommender import generate_recommendation
from app.tests.conftest import ctx_for


@pytest.mark.asyncio
async def test_payload_carries_both_workouts(session, two_athletes, monkeypatch):
    a, _ = two_athletes
    ctx = ctx_for(a)

    # FTP disponível + twin com intensity_split -> deve gerar os dois treinos.
    monkeypatch.setattr(
        "app.services.ai.recommender.FtpRepository.value_on",
        lambda self, d, aid: 250.0,
    )
    monkeypatch.setattr(
        "app.services.ai.recommender.TrainingWeekRepository.block_on",
        lambda self, d, aid: BlockType.BASE,
    )
    # profile com twin_seed
    from app.models.athlete import AthleteProfile
    prof = AthleteProfile(
        athlete_id=a.id, birth_date=date(1990, 1, 1), sex="M", weight_kg=70,
        height_cm=175, max_hr=185, primary_discipline="XCM", years_training=5,
        goals="ultra", weekly_hours=10,
        twin_seed={"intensity_split": {"z1_pct": 0.68, "z2_pct": 0.29, "z3_pct": 0.03}},
    )
    session.add(prof)
    await session.flush()

    rec = await generate_recommendation(session, ctx, a.id, target_date=date(2026, 7, 7))
    assert rec.payload.get("structured_workout") is not None
    assert rec.payload.get("methodology_workout") is not None
    assert isinstance(rec.payload.get("methodology_workout_description"), str)
    # Nome reflete o estilo do atleta (pirâmidal -> endurance).
    assert "padrão" in rec.payload["methodology_workout"]["name"].lower()
```

Nota: se o LLM mock não estiver configurado nos testes, o recommender já degrada
(usa `LlmClient` mock provider — ver `llm_provider=mock` no settings de teste).

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_ai/test_comparative_payload.py -q --no-header -p no:warnings"`
Expected: FAIL — `methodology_workout` ausente no payload

- [ ] **Step 3: Implementar**

Em `backend/app/services/ai/recommender.py`:

1. Imports (junto dos outros de workout):

```python
from app.services.workout.methodology_builder import (
    build_methodology_workout,
    typical_duration_for,
)
from app.models.workout import WorkoutCompleted
from sqlalchemy import select
from datetime import timedelta
```

2. No `generate_recommendation`, logo após o bloco que monta `structured_workout`
(depois da linha `workout_description = workout_analysis.describe(workout)`),
adicionar a geração do treino tradicional:

```python
    methodology_workout = None
    methodology_workout_description = None
    seed = (profile.twin_seed if profile is not None else None) or {}
    split = seed.get("intensity_split")
    if ftp_watts and split:
        # Duração típica: mediana das durações dos treinos concluídos nos últimos 90d.
        since = target_date - timedelta(days=90)
        rows = await session.execute(
            select(WorkoutCompleted.duration_s).where(
                WorkoutCompleted.athlete_id == athlete_id,
                WorkoutCompleted.workout_date >= since,
                WorkoutCompleted.deleted_at.is_(None),
            )
        )
        durations = [int(d) for (d,) in rows.all() if d]
        typical_s = typical_duration_for(durations, block)
        mw = build_methodology_workout(split, block, ftp_watts, typical_s, safety.risk_level)
        methodology_workout = mw.model_dump(mode="json")
        methodology_workout_description = workout_analysis.describe(mw)
```

3. Passar o treino tradicional ao prompt: na chamada `prompts.render_daily_workout(...)`,
adicionar o argumento:

```python
        methodology_workout=methodology_workout_description or "n/d",
```

4. No dict `payload=` da `AiRecommendation`, adicionar as duas chaves (após
`"workout_description": workout_description,`):

```python
            "methodology_workout": methodology_workout,
            "methodology_workout_description": methodology_workout_description,
```

Em `backend/app/services/ai/prompts.py`:

1. Adicionar o bloco de contraste ao `DAILY_WORKOUT_TEMPLATE` (após o bloco
`{methodology}` e antes de `Athlete digital-twin snapshot:`):

```
Traditional-method workout (what this athlete's own historical methodology would
prescribe today — reverse-engineered from their real training):
{methodology_workout}

When you write the recommendation, explicitly CONTRAST your recommended session
with this traditional-method one: name what the traditional method would do, then
what you recommend and WHY it differs (or say plainly if they coincide today).
```

2. `render_daily_workout` ganha o parâmetro `methodology_workout: str = "n/d"` e o
repassa ao `.format(...)`.

3. Subir a versão do template para 5: em `ACTIVE_TEMPLATES`, trocar
`"daily_workout": (4, ...)` por `"daily_workout": (5, DAILY_WORKOUT_TEMPLATE)`.

- [ ] **Step 4: Rodar e ver passar (+ regressão de recs)**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_ai -q --no-header -p no:warnings; ruff check app/services/ai/recommender.py app/services/ai/prompts.py app/tests/test_ai/test_comparative_payload.py"`
Expected: verde + `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/recommender.py backend/app/services/ai/prompts.py backend/app/tests/test_ai/test_comparative_payload.py
git commit -m "feat(recs): recommender gera o treino tradicional + prompt contrastivo (v5)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Export e escolha por variante (API + Garmin job)

**Files:**
- Modify: `backend/app/api/routes/recommendations.py` (export `variant` + decision `chosen_variant`)
- Modify: `backend/app/schemas/ai.py` (`DecisionRequest.chosen_variant`)
- Modify: `backend/app/jobs/garmin_job.py` (`_do_push_recommendation` lê a variante)
- Test: `backend/app/tests/test_garmin/test_push_variant.py` e ajuste em `test_api`/recs de export

**Interfaces:**
- Consumes: payload com `structured_workout` e `methodology_workout` (Task 2).
- Produces: `GET /recommendations/{id}/export.zwo?variant=methodology` (e `.fit`) lê `methodology_workout`; default `ai` lê `structured_workout` (inalterado). `DecisionRequest.chosen_variant: Literal["ai","methodology"] = "ai"`. Na aceitação, a variante escolhida é gravada no payload (`payload["chosen_variant"]`) e o push do Garmin usa o treino correspondente.

- [ ] **Step 1: Escrever o teste que falha**

Criar `backend/app/tests/test_garmin/test_push_variant.py`:

```python
"""Push do Garmin usa o treino da variante escolhida no aceite."""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.ai import AiRecommendation
from app.models.enums import RecommendationDecision, RiskLevel
from app.services.garmin.fake_client import FakeGarminClient
from app.jobs.garmin_job import _do_push_recommendation
from app.tests.conftest import ctx_for


def _rec(a, chosen: str) -> AiRecommendation:
    ai_wo = {"name": "IA", "sport": "cycling", "elements": [
        {"intensity": "active", "duration_s": 3600, "target": {"type": "power_pct_ftp", "low": 0.6, "high": 0.68}}
    ], "ftp_watts": 250.0}
    trad_wo = {"name": "Tradicional", "sport": "cycling", "elements": [
        {"intensity": "active", "duration_s": 5400, "target": {"type": "power_pct_ftp", "low": 0.62, "high": 0.68}}
    ], "ftp_watts": 250.0}
    return AiRecommendation(
        athlete_id=a.id, target_date=date(2026, 7, 7), kind="daily_workout",
        summary="s", rationale="r", risk_level=RiskLevel.LOW,
        decision=RecommendationDecision.ACCEPTED,
        payload={"structured_workout": ai_wo, "methodology_workout": trad_wo, "chosen_variant": chosen},
    )


@pytest.mark.asyncio
async def test_push_uses_methodology_when_chosen(session, two_athletes, monkeypatch):
    a, _ = two_athletes
    # feature ligada + conexão conectada são exigidas; mocka os gates.
    import app.jobs.garmin_job as gj
    monkeypatch.setattr(gj.token_store, "is_enabled", lambda: True)
    # (o teste foca em qual treino é escolhido; o push real usa FakeGarminClient)
    # ... (o implementer completa os mocks de conexão/sync_push seguindo test_export_wiring.py)
```

Nota ao implementer: siga o padrão de mocks já usado em
`app/tests/test_garmin/test_export_wiring.py` (conexão CONNECTED + captura do
StructuredWorkout empurrado). O asserto-chave: quando `chosen_variant ==
"methodology"`, o `name` do treino empurrado é "Tradicional"; default `ai` →
"IA". Complete os mocks de `GarminConnectionRepository`/`sync_push` conforme
aquele arquivo.

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_garmin/test_push_variant.py -q --no-header -p no:warnings"`
Expected: FAIL — o push sempre usa `structured_workout`

- [ ] **Step 3: Implementar**

Em `backend/app/schemas/ai.py`, no `DecisionRequest`:

```python
from typing import Literal
...
class DecisionRequest(BaseModel):
    decision: RecommendationDecision
    modified_payload: dict | None = None
    comment: str | None = None
    chosen_variant: Literal["ai", "methodology"] = "ai"
```

Em `backend/app/api/routes/recommendations.py`:

1. As duas rotas de export ganham `variant`. Trocar o corpo de `export.zwo` e
`export.fit` para escolher a chave do payload:

```python
async def export_recommendation_zwo(
    rec_id: uuid.UUID,
    variant: str = "ai",
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    repo = RecommendationRepository(db, ctx)
    rec = await repo.get(rec_id)
    key = "methodology_workout" if variant == "methodology" else "structured_workout"
    sw_data = (rec.payload or {}).get(key) if rec else None
    if not sw_data:
        raise HTTPException(status_code=404, detail="No structured workout for this recommendation")
    return _zwo_response(StructuredWorkout.model_validate(sw_data))
```

(fazer a mudança análoga em `export.fit`, usando a mesma seleção de `key`.)

2. Na `record_decision`, ANTES de enfileirar o push, gravar a variante escolhida
no payload (reassign para o SQLAlchemy detectar a mudança de JSONB):

```python
    rec.decision = body.decision
    if body.decision == RecommendationDecision.ACCEPTED:
        rec.payload = {**(rec.payload or {}), "chosen_variant": body.chosen_variant}
    db.add(rec)
```

Em `backend/app/jobs/garmin_job.py`, no `_do_push_recommendation`, trocar a
seleção do treino a empurrar:

```python
        variant = (rec.payload or {}).get("chosen_variant", "ai")
        key = "methodology_workout" if variant == "methodology" else "structured_workout"
        sw_data = (rec.payload or {}).get(key)
        if not sw_data:
            return {"status": "skipped", "reason": "no_structured_workout"}

        sw = StructuredWorkout.model_validate(sw_data)
```

(substitui o bloco atual que lê fixo `rec.payload["structured_workout"]`.)

- [ ] **Step 4: Rodar e ver passar (+ regressão garmin)**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_garmin app/tests/test_api -q --no-header -p no:warnings; ruff check app/api/routes/recommendations.py app/schemas/ai.py app/jobs/garmin_job.py app/tests/test_garmin/test_push_variant.py"`
Expected: verde + `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/recommendations.py backend/app/schemas/ai.py backend/app/jobs/garmin_job.py backend/app/tests/test_garmin/test_push_variant.py
git commit -m "feat(recs): export ?variant e escolha do treino (ai|methodology) no aceite

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Frontend — dois cards + escolha

**Files:**
- Modify: `web/lib/recs.ts` (helpers do treino tradicional)
- Modify: `web/components/recs/RecsSections.tsx` (card parametrizado por variante)
- Modify: `web/components/recs/RecomendacoesView.tsx` (dois cards + "Usar este")
- Test: `web/components/recs/__tests__/ComparativeWorkouts.test.tsx`

**Interfaces:**
- Consumes: `payload.structured_workout`/`methodology_workout` + descrições (Task 2); export `?variant` e decision `chosen_variant` (Task 3).
- Produces: dois cards lado a lado quando há `methodology_workout`; um só quando ausente. Botão "Usar este" posta `recommendations/{id}/decision` com `{decision:"ACCEPTED", chosen_variant}`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `web/components/recs/__tests__/ComparativeWorkouts.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { ComparativeWorkouts } from '@/components/recs/RecsSections'
import { apiFetch } from '@/lib/api'
import type { Recommendation } from '@/lib/types'

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))

const wo = (name: string) => ({ name, sport: 'cycling', elements: [], ftp_watts: 250 })
function rec(over: Record<string, unknown> = {}): Recommendation {
  return {
    id: 'r1', target_date: null, kind: 'daily_workout', summary: 's',
    physiological_objective: null, block_relation: null, rationale: null,
    adjust_if_tired: null, adjust_if_less_time: null,
    payload: { structured_workout: wo('IA'), workout_description: 'IA desc',
      methodology_workout: wo('Trad'), methodology_workout_description: 'Trad desc', ...over },
    risk_level: 'LOW', risk_flags: null, confidence: null, confidence_rationale: null,
    decision: 'PENDING', created_at: '2026-07-07T00:00:00Z', evidence: [],
  } as Recommendation
}

beforeEach(() => vi.clearAllMocks())

describe('ComparativeWorkouts', () => {
  it('mostra os dois cards quando há treino tradicional', () => {
    render(<ComparativeWorkouts rec={rec()} onChosen={() => {}} />)
    expect(screen.getByText(/Método tradicional/)).toBeInTheDocument()
    expect(screen.getByText(/Recomendação da IA/)).toBeInTheDocument()
    expect(screen.getByText('Trad desc')).toBeInTheDocument()
    expect(screen.getByText('IA desc')).toBeInTheDocument()
  })

  it('sem treino tradicional mostra só um card', () => {
    render(<ComparativeWorkouts rec={rec({ methodology_workout: undefined, methodology_workout_description: undefined })} onChosen={() => {}} />)
    expect(screen.queryByText(/Método tradicional/)).not.toBeInTheDocument()
    expect(screen.getByText(/Treino/)).toBeInTheDocument()
  })

  it('"Usar este" no tradicional posta decision com chosen_variant methodology', async () => {
    ;(apiFetch as Mock).mockResolvedValue({ ok: true, json: async () => ({}) } as Response)
    render(<ComparativeWorkouts rec={rec()} onChosen={() => {}} />)
    fireEvent.click(screen.getAllByRole('button', { name: /Usar este/ })[0])
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
      'recommendations/r1/decision',
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('methodology') }),
    ))
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/recs/__tests__/ComparativeWorkouts.test.tsx`
Expected: FAIL — `ComparativeWorkouts` inexistente

- [ ] **Step 3: Implementar**

Em `web/lib/recs.ts`, adicionar ao final:

```ts
export function methodologyWorkoutDescription(payload: Record<string, unknown> | null): string | null {
  const d = payload?.methodology_workout_description
  return typeof d === 'string' && d.trim() ? d : null
}

export function hasMethodologyWorkout(payload: Record<string, unknown> | null): boolean {
  return !!payload?.methodology_workout
}
```

Em `web/components/recs/RecsSections.tsx`, adicionar (após o componente
`StructuredWorkout` existente) um card comparativo. Imports no topo do arquivo:
`import { apiFetch } from '@/lib/api'`, `import { useState } from 'react'`, e os
helpers `methodologyWorkoutDescription, hasMethodologyWorkout, workoutDescription, hasStructured` de `@/lib/recs`.

```tsx
function WorkoutColumn({
  title, desc, hasDl, recId, variant, onUse, busy,
}: {
  title: string; desc: string | null; hasDl: boolean; recId: string
  variant: 'ai' | 'methodology'; onUse: () => void; busy: boolean
}) {
  return (
    <Card title={title}>
      {desc && (
        <pre className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-700 dark:bg-slate-800/60 dark:text-slate-200">{desc}</pre>
      )}
      {hasDl && (
        <div className="mt-3 flex flex-wrap gap-2">
          {[['zwo', 'TrainingPeaks'], ['fit', 'dispositivo']].map(([ext, hint]) => (
            <a
              key={ext}
              href={`/api/proxy/recommendations/${recId}/export.${ext}?variant=${variant}`}
              download={`treino_${variant}_${recId.slice(0, 8)}.${ext}`}
              className="rounded-lg border border-slate-300 px-3 py-1 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              ⬇️ .{ext} ({hint})
            </a>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={onUse}
        disabled={busy}
        className="mt-3 w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        Usar este
      </button>
    </Card>
  )
}

export function ComparativeWorkouts({ rec, onChosen }: { rec: Recommendation; onChosen: () => void }) {
  const [busy, setBusy] = useState(false)
  const aiDesc = workoutDescription(rec.payload)
  const aiHas = hasStructured(rec.payload)
  const tradDesc = methodologyWorkoutDescription(rec.payload)
  const tradHas = hasMethodologyWorkout(rec.payload)

  async function choose(variant: 'ai' | 'methodology') {
    setBusy(true)
    try {
      await apiFetch(`recommendations/${rec.id}/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision: 'ACCEPTED', chosen_variant: variant }),
      })
      onChosen()
    } finally {
      setBusy(false)
    }
  }

  if (!tradHas) {
    // Compat: sem treino tradicional -> um card só (comportamento antigo).
    if (!aiDesc && !aiHas) return null
    return (
      <div className="grid grid-cols-1 gap-4">
        <WorkoutColumn title="🏋️ Treino" desc={aiDesc} hasDl={aiHas} recId={rec.id} variant="ai" onUse={() => choose('ai')} busy={busy} />
      </div>
    )
  }
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <WorkoutColumn title="🏛️ Método tradicional" desc={tradDesc} hasDl={tradHas} recId={rec.id} variant="methodology" onUse={() => choose('methodology')} busy={busy} />
      <WorkoutColumn title="🤖 Recomendação da IA" desc={aiDesc} hasDl={aiHas} recId={rec.id} variant="ai" onUse={() => choose('ai')} busy={busy} />
    </div>
  )
}
```

Em `web/components/recs/RecomendacoesView.tsx`: substituir `<StructuredWorkout rec={rec} />`
por `<ComparativeWorkouts rec={rec} onChosen={() => void mutate()} />` e ajustar
o import de `@/components/recs/RecsSections` para incluir `ComparativeWorkouts`
(pode remover `StructuredWorkout` do import se não for mais usado).

- [ ] **Step 4: Rodar e ver passar (suíte web completa + tsc)**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: toda a suíte web verde; `tsc` sem erros

- [ ] **Step 5: Commit**

```bash
git add web/lib/recs.ts web/components/recs/RecsSections.tsx web/components/recs/RecomendacoesView.tsx web/components/recs/__tests__/ComparativeWorkouts.test.tsx
git commit -m "feat(web): dois treinos lado a lado (tradicional vs IA) + Usar este

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
