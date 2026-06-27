# Feedback por Tipo de Treino — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar o eixo de agregação do feedback do atleta de *bloco de periodização* para *tipo de treino* (`WorkoutType`), consistente nos dois fluxos de geração.

**Architecture:** O tipo é derivado deterministicamente de bloco+risco no fluxo diário (espelhando `build_for`) e lido do tipo real do planejado no ajuste-do-dia. Ambos gravam `payload.signals.workout_type` (jsonb, sem migração). `feedback_context` passa a agregar por esse campo.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Pydantic v2, pytest/pytest-asyncio. Frontend Streamlit (não tocado neste plano).

## Global Constraints

- Sem migração de banco: o eixo vive em `payload.signals` (jsonb), nunca em coluna.
- Sem mudança de frontend: `intelligence_view.feedback_line` não lê o eixo por-tipo.
- Valores de `signals.workout_type` são a **string** do enum (`WorkoutType.X.value`), nunca o objeto enum.
- TAPER → `WorkoutType.OTHER` (template `openers` = ativação, não estímulo de carga).
- Override de risco: `RiskLevel.HIGH` força `WorkoutType.RECOVERY`, ganhando do bloco — mesma precedência de `build_for`.
- Recs antigas (só `signals.block`) degradam para o balde `"—"`, fora da linha "Por tipo:".
- Backend tests rodam via Docker:
  `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -v"`

---

### Task 1: Derivação do tipo de treino (bloco+risco)

**Files:**
- Modify: `backend/app/services/workout/templates.py` (adicionar mapa `BLOCK_WORKOUT_TYPE` após o dict `TEMPLATES`, ~linha 90)
- Modify: `backend/app/services/workout/builder.py` (adicionar `workout_type_for` após `build_for`)
- Test: `backend/app/tests/test_workout/test_builder.py` (adicionar testes)

**Interfaces:**
- Consumes: `BlockType`, `RiskLevel`, `WorkoutType` de `app.models.enums`.
- Produces: `workout_type_for(block_type: BlockType, risk_level: RiskLevel) -> WorkoutType` em `app.services.workout.builder`; mapa `BLOCK_WORKOUT_TYPE: dict[BlockType, WorkoutType]` em `app.services.workout.templates`.

- [ ] **Step 1: Write the failing test**

Adicionar ao final de `backend/app/tests/test_workout/test_builder.py`:

```python
from app.models.enums import WorkoutType
from app.services.workout.builder import workout_type_for


def test_workout_type_for_maps_each_block():
    assert workout_type_for(BlockType.BASE, RiskLevel.LOW) == WorkoutType.ENDURANCE
    assert workout_type_for(BlockType.BUILD, RiskLevel.LOW) == WorkoutType.SWEET_SPOT
    assert workout_type_for(BlockType.PEAK, RiskLevel.LOW) == WorkoutType.VO2MAX
    assert workout_type_for(BlockType.TAPER, RiskLevel.LOW) == WorkoutType.OTHER
    assert workout_type_for(BlockType.RECOVERY, RiskLevel.LOW) == WorkoutType.RECOVERY


def test_workout_type_for_high_risk_forces_recovery_over_block():
    for block in BlockType:
        assert workout_type_for(block, RiskLevel.HIGH) == WorkoutType.RECOVERY


def test_workout_type_for_moderate_keeps_block_type():
    # MODERATE reduz volume mas não muda o tipo de estímulo
    assert workout_type_for(BlockType.BUILD, RiskLevel.MODERATE) == WorkoutType.SWEET_SPOT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_workout/test_builder.py -v"`
Expected: FAIL com `ImportError: cannot import name 'workout_type_for'`

- [ ] **Step 3: Add the BLOCK_WORKOUT_TYPE map**

Em `backend/app/services/workout/templates.py`, ajustar o import da linha 11 e adicionar o mapa logo após o dict `TEMPLATES` (que termina ~linha 91).

Trocar a linha de import:

```python
from app.models.enums import BlockType
```

por:

```python
from app.models.enums import BlockType, WorkoutType
```

Adicionar após o fechamento de `TEMPLATES`:

```python
# Tipo de estímulo de cada bloco (paralelo a TEMPLATES). Usado para agregar
# feedback por tipo de treino. TAPER usa 'openers' (ativação) -> OTHER.
BLOCK_WORKOUT_TYPE: dict[BlockType, WorkoutType] = {
    BlockType.BASE: WorkoutType.ENDURANCE,
    BlockType.BUILD: WorkoutType.SWEET_SPOT,
    BlockType.PEAK: WorkoutType.VO2MAX,
    BlockType.TAPER: WorkoutType.OTHER,
    BlockType.RECOVERY: WorkoutType.RECOVERY,
}
```

- [ ] **Step 4: Add workout_type_for to builder.py**

Em `backend/app/services/workout/builder.py`, ajustar imports e adicionar a função ao final.

Trocar a linha 9:

```python
from app.models.enums import BlockType, RiskLevel
```

por:

```python
from app.models.enums import BlockType, RiskLevel, WorkoutType
```

Trocar a linha 10:

```python
from app.services.workout import analysis, templates
```

por:

```python
from app.services.workout import analysis, templates
from app.services.workout.templates import BLOCK_WORKOUT_TYPE
```

Adicionar ao final do arquivo:

```python
def workout_type_for(block_type: BlockType, risk_level: RiskLevel) -> WorkoutType:
    """Tipo de estímulo do treino diário, derivado de bloco+risco.

    Espelha a seleção de template de build_for: risco HIGH força RECOVERY
    (mesmo override que troca o template para `recovery`); caso contrário o
    tipo segue o bloco. Bloco desconhecido cai em ENDURANCE (default seguro,
    igual ao TEMPLATES.get(..., endurance))."""
    if risk_level == RiskLevel.HIGH:
        return WorkoutType.RECOVERY
    return BLOCK_WORKOUT_TYPE.get(block_type, WorkoutType.ENDURANCE)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_workout/test_builder.py -v"`
Expected: PASS (todos, incl. os 3 novos)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/workout/templates.py backend/app/services/workout/builder.py backend/app/tests/test_workout/test_builder.py
git commit -m "feat(workout): workout_type_for — deriva tipo de treino de bloco+risco"
```

---

### Task 2: Gravar signals.workout_type nos dois fluxos

**Files:**
- Modify: `backend/app/services/ai/recommender.py` (import + 2 pontos de wiring)
- Test: `backend/app/tests/test_ai/test_feedback_wiring.py` (asserir workout_type nos signals)

**Interfaces:**
- Consumes: `workout_type_for` da Task 1; `generate_recommendation`, `generate_day_adjustment` existentes.
- Produces: `payload.signals.workout_type` (string) presente em ambos os fluxos — consumido pela Task 3.

- [ ] **Step 1: Write the failing test**

Adicionar ao final de `backend/app/tests/test_ai/test_feedback_wiring.py`:

```python
async def test_daily_recommendation_signals_carry_workout_type(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    session.add(FtpHistory(athlete_id=a.id, created_by=a.id, ftp_watts=240.0,
                           valid_from=date(2026, 1, 1)))
    await session.flush()
    rec = await generate_recommendation(session, ctx, a.id,
                                        target_date=date(2026, 6, 23), kind="daily_workout")
    wt = (rec.payload or {}).get("signals", {}).get("workout_type")
    assert wt is not None
    assert isinstance(wt, str)  # valor string do enum, nunca o objeto


async def test_day_adjustment_signals_carry_planned_workout_type(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    w = WorkoutPlanned(
        athlete_id=a.id, created_by=a.id,
        planned_date=date.today() + timedelta(days=1), name="Endurance",
        workout_type=WorkoutType.ENDURANCE,
        structure={"name": "Endurance", "sport": "cycling", "elements": [
            {"intensity": "active", "duration_s": 1200,
             "target": {"type": "power_pct_ftp", "low": 0.65, "high": 0.68}}]},
    )
    session.add(w)
    await session.flush()
    rec = await generate_day_adjustment(session, ctx, a.id, workout_planned=w)
    wt = (rec.payload or {}).get("signals", {}).get("workout_type")
    assert wt == "ENDURANCE"  # tipo REAL do planejado, não derivado
```

Adicionar o import de `WorkoutType` no topo do arquivo (junto aos imports de enums existentes, linha 6):

```python
from app.models.enums import RecommendationDecision, RiskLevel, WorkoutType
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_feedback_wiring.py -v"`
Expected: FAIL — `assert wt is not None` (workout_type ainda não é gravado)

- [ ] **Step 3: Import workout_type_for no recommender**

Em `backend/app/services/ai/recommender.py`, localizar o import existente de `build_for` (usado em `build_for(block, ...)`). Ele importa de `app.services.workout.builder`. Adicionar `workout_type_for` ao mesmo import. Ex.: se a linha é

```python
from app.services.workout.builder import build_for
```

trocar por:

```python
from app.services.workout.builder import build_for, workout_type_for
```

- [ ] **Step 4: Gravar workout_type no fluxo diário**

Em `generate_recommendation`, localizar (≈ linha 136-137):

```python
    signals = _signals(twin.snapshot, methodology, block, ftp_watts)
    signals["feedback"] = feedback_stats
```

Trocar por:

```python
    signals = _signals(twin.snapshot, methodology, block, ftp_watts)
    signals["feedback"] = feedback_stats
    signals["workout_type"] = workout_type_for(block, safety.risk_level).value
```

- [ ] **Step 5: Gravar workout_type no fluxo de ajuste-do-dia**

Em `generate_day_adjustment`, localizar (≈ linha 247-248):

```python
    signals = _signals(twin.snapshot, methodology, block, ftp_watts)
    signals["feedback"] = feedback_stats
```

Trocar por:

```python
    planned_type = getattr(workout_planned.workout_type, "value",
                           workout_planned.workout_type)
    signals = _signals(twin.snapshot, methodology, block, ftp_watts)
    signals["feedback"] = feedback_stats
    signals["workout_type"] = planned_type
```

Em seguida, no dict `payload` do mesmo fluxo, localizar dentro de `planned_snapshot` (≈ linha 264-265):

```python
                "workout_type": getattr(workout_planned.workout_type, "value",
                                        workout_planned.workout_type),
```

Trocar por (reusa a variável, evita recomputar — DRY):

```python
                "workout_type": planned_type,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_feedback_wiring.py -v"`
Expected: PASS (todos, incl. os 2 novos)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/ai/recommender.py backend/app/tests/test_ai/test_feedback_wiring.py
git commit -m "feat(ai): grava signals.workout_type (derivado na diaria, real no ajuste)"
```

---

### Task 3: Agregar feedback por tipo de treino

**Files:**
- Modify: `backend/app/services/ai/feedback_context.py` (FeedbackItem, summarize, feedback_summary)
- Test: `backend/app/tests/test_ai/test_feedback_context.py` (block → workout_type)

**Interfaces:**
- Consumes: `payload.signals.workout_type` gravado pela Task 2 (e seedado direto nos testes).
- Produces: `summarize(items) -> (str, dict)` com stats `by_workout_type` e texto "Por tipo:"; `FeedbackItem(rating, made_sense, comment, workout_type, when)`.

- [ ] **Step 1: Update the tests (these define the new behavior)**

Substituir o conteúdo de `backend/app/tests/test_ai/test_feedback_context.py` por:

```python
import uuid
import pytest
from datetime import date

from app.core.tenant import TenantContext
from app.models.ai import AiRecommendation, AiRecommendationFeedback
from app.models.enums import RecommendationDecision, RiskLevel
from app.services.ai.feedback_context import FeedbackItem, summarize, feedback_summary


def _ctx(aid):
    from app.models.enums import Role
    return TenantContext(athlete_id=aid, tenant_id="t", role=Role.ATHLETE)


async def _seed_feedback(session, aid, *, rating, made_sense, comment, workout_type):
    rec = AiRecommendation(
        athlete_id=aid, target_date=date(2026, 6, 20), kind="daily_workout",
        summary="s", risk_level=RiskLevel.LOW, decision=RecommendationDecision.PENDING,
        payload={"signals": {"workout_type": workout_type}},
    )
    session.add(rec)
    await session.flush()
    session.add(AiRecommendationFeedback(
        athlete_id=aid, recommendation_id=rec.id, rating=rating,
        made_sense=made_sense, comment=comment,
    ))
    await session.flush()


def _items():
    # mais recente primeiro
    return [
        FeedbackItem(5, True, "perfeito", "ENDURANCE", date(2026, 6, 20)),
        FeedbackItem(3, False, "muito puxado no fim", "VO2MAX", date(2026, 6, 12)),
        FeedbackItem(4, True, None, "VO2MAX", date(2026, 6, 5)),
    ]


def test_summarize_aggregates_overall_and_by_workout_type():
    text, stats = summarize(_items())
    assert stats["count"] == 3
    assert stats["avg_rating"] == 4.0
    assert stats["made_sense_pct"] == 67  # 2 responderam made_sense, 2 True -> 67%
    assert stats["by_workout_type"]["VO2MAX"]["count"] == 2
    assert stats["by_workout_type"]["VO2MAX"]["avg_rating"] == 3.5
    assert "Feedback recente (3 avaliações, nota média 4.0" in text
    assert "Por tipo:" in text


def test_summarize_includes_recent_comments_with_label():
    text, _ = summarize(_items(), comment_limit=5)
    assert "[2026-06-20 · ENDURANCE] perfeito" in text
    assert "[2026-06-12 · VO2MAX] muito puxado no fim" in text


def test_summarize_respects_comment_limit_most_recent_first():
    text, _ = summarize(_items(), comment_limit=1)
    assert "perfeito" in text          # mais recente
    assert "muito puxado" not in text  # cortado pelo limite


def test_summarize_empty_is_nd():
    assert summarize([]) == ("n/d", {})


def test_summarize_type_none_groups_under_dash():
    text, stats = summarize([FeedbackItem(4, None, None, None, date(2026, 6, 1))])
    assert stats["by_workout_type"]["—"]["count"] == 1
    assert stats["made_sense_pct"] is None   # ninguém respondeu made_sense
    assert "Por tipo:" not in text           # "—" não vira recorte textual


@pytest.mark.asyncio
async def test_feedback_summary_reads_and_aggregates(session):
    aid = uuid.uuid4()
    await _seed_feedback(session, aid, rating=5, made_sense=True, comment="bom", workout_type="ENDURANCE")
    await _seed_feedback(session, aid, rating=3, made_sense=False, comment="puxado", workout_type="VO2MAX")
    text, stats = await feedback_summary(session, _ctx(aid), aid)
    assert stats["count"] == 2
    assert stats["by_workout_type"]["VO2MAX"]["count"] == 1
    assert "Feedback recente (2 avaliações" in text
    assert "bom" in text or "puxado" in text


@pytest.mark.asyncio
async def test_feedback_summary_empty_is_nd(session):
    aid = uuid.uuid4()
    assert await feedback_summary(session, _ctx(aid), aid) == ("n/d", {})


@pytest.mark.asyncio
async def test_feedback_summary_isolated_per_athlete(session):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed_feedback(session, a, rating=5, made_sense=True, comment="de A", workout_type="ENDURANCE")
    text_b, stats_b = await feedback_summary(session, _ctx(b), b)
    assert (text_b, stats_b) == ("n/d", {})  # B não vê o feedback de A
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_feedback_context.py -v"`
Expected: FAIL — `KeyError: 'by_workout_type'` (stats ainda usa `by_block`)

- [ ] **Step 3: Update FeedbackItem and summarize**

Em `backend/app/services/ai/feedback_context.py`, no dataclass `FeedbackItem` (≈ linha 23-29), trocar o campo `block`:

```python
@dataclass
class FeedbackItem:
    rating: int
    made_sense: bool | None
    comment: str | None
    block: str | None
    when: date
```

por:

```python
@dataclass
class FeedbackItem:
    rating: int
    made_sense: bool | None
    comment: str | None
    workout_type: str | None
    when: date
```

Em `summarize` (≈ linhas 45-81), trocar o bloco de agrupamento e o texto. Localizar:

```python
    overall = _rate(items)
    by_block: dict[str, dict] = {}
    grouped: dict[str, list[FeedbackItem]] = {}
    for i in items:
        grouped.setdefault(i.block or "—", []).append(i)
    for block, group in grouped.items():
        by_block[block] = _rate(group)

    comments: list[str] = []
    for i in items:
        if i.comment and i.comment.strip():
            comments.append(f"[{i.when.isoformat()} · {i.block or '—'}] {i.comment.strip()}")
        if len(comments) >= comment_limit:
            break

    stats = {**overall, "by_block": by_block}
```

Trocar por:

```python
    overall = _rate(items)
    by_workout_type: dict[str, dict] = {}
    grouped: dict[str, list[FeedbackItem]] = {}
    for i in items:
        grouped.setdefault(i.workout_type or "—", []).append(i)
    for wtype, group in grouped.items():
        by_workout_type[wtype] = _rate(group)

    comments: list[str] = []
    for i in items:
        if i.comment and i.comment.strip():
            comments.append(f"[{i.when.isoformat()} · {i.workout_type or '—'}] {i.comment.strip()}")
        if len(comments) >= comment_limit:
            break

    stats = {**overall, "by_workout_type": by_workout_type}
```

Logo abaixo, localizar a montagem da linha por-bloco:

```python
    block_bits = []
    for block, s in by_block.items():
        if block == "—":
            continue
        bit = f"{block} {s['avg_rating']}/5"
        if s["made_sense_pct"] is not None:
            bit += f" ({s['made_sense_pct']}% fez sentido)"
        block_bits.append(bit)
    if block_bits:
        parts.append("Por bloco: " + ", ".join(block_bits))
```

Trocar por:

```python
    type_bits = []
    for wtype, s in by_workout_type.items():
        if wtype == "—":
            continue
        bit = f"{wtype} {s['avg_rating']}/5"
        if s["made_sense_pct"] is not None:
            bit += f" ({s['made_sense_pct']}% fez sentido)"
        type_bits.append(bit)
    if type_bits:
        parts.append("Por tipo: " + ", ".join(type_bits))
```

- [ ] **Step 4: Update feedback_summary read**

Em `feedback_summary` (≈ linha 108-114), localizar o loop que monta os items:

```python
    for fb, rec in rows:
        block = ((rec.payload or {}).get("signals") or {}).get("block")
        when = (fb.created_at or datetime.now(timezone.utc)).date()
        items.append(FeedbackItem(
            rating=fb.rating, made_sense=fb.made_sense,
            comment=fb.comment, block=block, when=when,
        ))
```

Trocar por:

```python
    for fb, rec in rows:
        workout_type = ((rec.payload or {}).get("signals") or {}).get("workout_type")
        when = (fb.created_at or datetime.now(timezone.utc)).date()
        items.append(FeedbackItem(
            rating=fb.rating, made_sense=fb.made_sense,
            comment=fb.comment, workout_type=workout_type, when=when,
        ))
```

Atualizar também a docstring do módulo (linhas 1-6) e de `summarize` se mencionarem "block"/"bloco": trocar referência ao recorte "por bloco" por "por tipo de treino".

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_feedback_context.py -v"`
Expected: PASS (todos)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ai/feedback_context.py backend/app/tests/test_ai/test_feedback_context.py
git commit -m "feat(ai): agrega feedback por tipo de treino (substitui eixo por bloco)"
```

---

### Task 4: Suíte completa de AI + verificação de regressão

**Files:**
- Test: `backend/app/tests/test_ai/` (suíte inteira) + `test_api/test_day_adjustment.py`

**Interfaces:**
- Consumes: tudo das Tasks 1-3.
- Produces: confirmação de que nada que lia `signals.block` quebrou.

- [ ] **Step 1: Grep por leitores remanescentes do eixo antigo**

Run (Grep tool ou): procurar por `by_block`, `"block"` em `signals`, e `.block` em FeedbackItem fora dos arquivos já alterados.

Expected: nenhum consumidor de `signals.block` para feedback fora do que foi migrado. (O `signals["block"]` gravado por `_signals` para o bloco de periodização **permanece** — é outro dado, não o eixo de feedback. Não remover.)

- [ ] **Step 2: Run the AI + day-adjustment suites**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai app/tests/test_workout app/tests/test_api/test_day_adjustment.py -v"`
Expected: PASS (0 failures)

- [ ] **Step 3: Run the full backend suite**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest -q"`
Expected: exit 0

- [ ] **Step 4: Commit (se houver ajuste residual)**

Caso o Step 1-3 exponha algum ajuste necessário (ex.: outro teste que seedava `signals.block` e dependia do recorte por bloco), corrigir mínimo e:

```bash
git add -A
git commit -m "test(ai): alinha asserts remanescentes ao eixo por tipo de treino"
```

Se nada extra for necessário, pular este commit.

---

## Self-Review

**Spec coverage:**
- Componente 1 (derivação `workout_type_for` + `BLOCK_WORKOUT_TYPE`) → Task 1 ✓
- Componente 2 (wiring nos dois fluxos) → Task 2 ✓
- Componente 3 (agregação block→tipo) → Task 3 ✓
- Compat. retroativa (balde "—") → Task 3 Step 1 `test_summarize_type_none_groups_under_dash` + `feedback_summary` lê `.get("workout_type")` (None em recs antigas) ✓
- Sem migração / sem frontend → Global Constraints + nenhuma task toca migração/frontend ✓
- TAPER→OTHER, HIGH→RECOVERY → Task 1 testes ✓
- Critérios de aceite 1-5 → Tasks 2 (signals nos 2 fluxos), 3 (by_workout_type/"Por tipo:"), 3 (compat), 4 (suíte verde) ✓

**Placeholder scan:** sem TBD/TODO; todo passo de código mostra o código exato. ✓

**Type consistency:** `workout_type_for(BlockType, RiskLevel) -> WorkoutType` usado idêntico nas Tasks 1-2; `FeedbackItem(..., workout_type, when)` consistente entre Task 3 def e usos; stats key `by_workout_type` idêntico em summarize, feedback_summary e testes. ✓
