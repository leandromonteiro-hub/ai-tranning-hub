# Feedback Ponderado por Recência (Decay Exponencial) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir a média aritmética simples do feedback por uma média ponderada por recência (decay exponencial, meia-vida 30d), no agregado geral e nos buckets por tipo.

**Architecture:** Uma função pura `_recency_weight(when, as_of)` calcula `0.5^(idade/30)`; `_rate` passa a ponderar média e percentual usando-a; `summarize` recebe `as_of` e o repassa; `feedback_summary` injeta `as_of=now.date()` (mantendo as funções de agregação puras). Transparência via relabel + marcas nos stats + label do frontend.

**Tech Stack:** Python 3.12, SQLAlchemy async, pytest/pytest-asyncio. Frontend Streamlit (um label).

## Global Constraints

- Decay exponencial por meia-vida: `w = 0.5^(idade_dias / 30)`. `_HALF_LIFE_DAYS = 30`.
- Idade negativa (data futura / skew de relógio) é clampada a 0 → peso 1.0.
- Pondera `avg_rating` e `made_sense_pct`; `count` permanece cru (inteiro).
- Funções de agregação (`summarize`, `_rate`, `_recency_weight`) são PURAS — nunca chamam `now()`. A data de referência `as_of: date` é injetada por `feedback_summary`.
- Janela `_DEFAULT_WINDOW_DAYS = 90` inalterada.
- Caso vazio `("n/d", {})` inalterado.
- Texto: head relabela para "nota média ponderada por recência". Stats ganham `weighted=True` e `half_life_days=30` no nível geral (não por bucket). Frontend `feedback_line`: "nota média" → "nota média ponderada".
- NÃO tocar o `summarize(plan)` de `test_planning/test_periodization.py` — é outra função (domínio de periodização), homônima.
- Backend tests rodam via Docker:
  `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -v"`
- Frontend tests rodam via Docker:
  `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest -q"`

---

### Task 1: Função pura de peso por recência

**Files:**
- Modify: `backend/app/services/ai/feedback_context.py` (constante `_HALF_LIFE_DAYS` + função `_recency_weight`)
- Test: `backend/app/tests/test_ai/test_feedback_context.py` (novos unit tests + import)

**Interfaces:**
- Consumes: `date` de `datetime` (já importado no módulo).
- Produces: `_HALF_LIFE_DAYS = 30`; `_recency_weight(when: date, as_of: date) -> float`.

- [ ] **Step 1: Write the failing test**

Adicionar ao final de `backend/app/tests/test_ai/test_feedback_context.py`:

```python
def test_recency_weight_today_is_one():
    from app.services.ai.feedback_context import _recency_weight
    assert _recency_weight(date(2026, 6, 30), date(2026, 6, 30)) == 1.0


def test_recency_weight_one_halflife_is_half():
    from app.services.ai.feedback_context import _recency_weight
    # 30 dias = uma meia-vida
    assert _recency_weight(date(2026, 5, 31), date(2026, 6, 30)) == pytest.approx(0.5)


def test_recency_weight_two_halflives_is_quarter():
    from app.services.ai.feedback_context import _recency_weight
    # 60 dias = duas meias-vidas
    assert _recency_weight(date(2026, 5, 1), date(2026, 6, 30)) == pytest.approx(0.25)


def test_recency_weight_future_date_clamps_to_one():
    from app.services.ai.feedback_context import _recency_weight
    # data futura (skew) → idade 0 → peso 1.0
    assert _recency_weight(date(2026, 7, 5), date(2026, 6, 30)) == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_feedback_context.py -k recency_weight -v"`
Expected: FAIL com `ImportError: cannot import name '_recency_weight'`

- [ ] **Step 3: Add the constant and function**

Em `backend/app/services/ai/feedback_context.py`, localizar:

```python
_DEFAULT_WINDOW_DAYS = 90
_DEFAULT_COMMENT_LIMIT = 5
```

Trocar por:

```python
_DEFAULT_WINDOW_DAYS = 90
_DEFAULT_COMMENT_LIMIT = 5
_HALF_LIFE_DAYS = 30
```

Adicionar a função logo após o dataclass `FeedbackItem` (antes de `_rate`):

```python
def _recency_weight(when: date, as_of: date) -> float:
    """Peso exponencial por recência: 0.5^(idade_dias / meia-vida).
    Idade negativa (data futura / skew de relógio) é tratada como 0 → peso 1.0."""
    age_days = max(0, (as_of - when).days)
    return 0.5 ** (age_days / _HALF_LIFE_DAYS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_feedback_context.py -k recency_weight -v"`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/feedback_context.py backend/app/tests/test_ai/test_feedback_context.py
git commit -m "feat(ai): _recency_weight — peso exponencial por recencia (meia-vida 30d)"
```

---

### Task 2: `_rate` ponderado + `summarize`/`feedback_summary` com `as_of`

**Files:**
- Modify: `backend/app/services/ai/feedback_context.py` (`_rate`, `summarize`, `feedback_summary`)
- Test: `backend/app/tests/test_ai/test_feedback_context.py` (atualizar chamadas existentes + novos testes)

**Interfaces:**
- Consumes: `_recency_weight(when, as_of) -> float` e `_HALF_LIFE_DAYS` da Task 1.
- Produces: `_rate(group: list[FeedbackItem], as_of: date) -> dict`; `summarize(items, comment_limit=_DEFAULT_COMMENT_LIMIT, *, as_of: date) -> tuple[str, dict]` (stats agora inclui `weighted: True`, `half_life_days: 30`); `feedback_summary` inalterada na assinatura pública.

- [ ] **Step 1: Update existing tests to the new signature + add weighting tests**

Em `backend/app/tests/test_ai/test_feedback_context.py`:

(a) O helper `_items()` e os testes que chamam `summarize(...)` precisam de `as_of`. Localizar `def _items()` e os testes `test_summarize_*` puros. Definir uma data de referência fixa no topo do bloco de testes puros e passá-la. Substituir o `_items()` e os testes puros existentes por:

```python
_AS_OF = date(2026, 6, 20)


def _items():
    # mais recente primeiro (datas relativas a _AS_OF)
    return [
        FeedbackItem(5, True, "perfeito", "ENDURANCE", date(2026, 6, 20)),
        FeedbackItem(3, False, "muito puxado no fim", "VO2MAX", date(2026, 6, 12)),
        FeedbackItem(4, True, None, "VO2MAX", date(2026, 6, 5)),
    ]


def test_summarize_aggregates_overall_and_by_workout_type():
    text, stats = summarize(_items(), as_of=_AS_OF)
    assert stats["count"] == 3
    # média PONDERADA por recência (o 5 de hoje puxa acima da média simples 4.0)
    assert stats["avg_rating"] == 4.1
    assert stats["weighted"] is True
    assert stats["half_life_days"] == 30
    assert stats["made_sense_pct"] == 67  # True(w1.0)+True(w.71) sobre True+False+True ponderado
    assert stats["by_workout_type"]["VO2MAX"]["count"] == 2
    assert stats["by_workout_type"]["VO2MAX"]["avg_rating"] == 3.5
    assert "Feedback recente (3 avaliações, nota média ponderada por recência 4.1" in text
    assert "Por tipo:" in text


def test_summarize_includes_recent_comments_with_label():
    text, _ = summarize(_items(), comment_limit=5, as_of=_AS_OF)
    assert "[2026-06-20 · ENDURANCE] perfeito" in text
    assert "[2026-06-12 · VO2MAX] muito puxado no fim" in text


def test_summarize_respects_comment_limit_most_recent_first():
    text, _ = summarize(_items(), comment_limit=1, as_of=_AS_OF)
    assert "perfeito" in text          # mais recente
    assert "muito puxado" not in text  # cortado pelo limite


def test_summarize_empty_is_nd():
    assert summarize([], as_of=_AS_OF) == ("n/d", {})


def test_summarize_type_none_groups_under_dash():
    text, stats = summarize([FeedbackItem(4, None, None, None, date(2026, 6, 1))], as_of=_AS_OF)
    assert stats["by_workout_type"]["—"]["count"] == 1
    assert stats["made_sense_pct"] is None   # ninguém respondeu made_sense
    assert "Por tipo:" not in text           # "—" não vira recorte textual


def test_summarize_weights_recent_feedback_more():
    as_of = date(2026, 6, 30)
    items = [
        FeedbackItem(5, True, None, "ENDURANCE", date(2026, 6, 30)),   # hoje, w=1.0
        FeedbackItem(1, True, None, "ENDURANCE", date(2026, 4, 1)),    # 90d atrás, w≈0.125
    ]
    _, stats = summarize(items, as_of=as_of)
    # média simples seria 3.0; ponderada favorece fortemente o 5 recente
    assert stats["avg_rating"] > 4.0


def test_summarize_same_age_equals_simple_mean():
    as_of = date(2026, 6, 30)
    items = [
        FeedbackItem(2, None, None, "ENDURANCE", date(2026, 6, 20)),
        FeedbackItem(4, None, None, "ENDURANCE", date(2026, 6, 20)),
    ]
    _, stats = summarize(items, as_of=as_of)
    assert stats["avg_rating"] == 3.0  # mesma idade → pesos se cancelam
```

(b) A função async `_seed_feedback` e os testes `test_feedback_summary_*` permanecem, mas o teste de leitura ganha uma asserção das marcas de ponderação. Localizar `test_feedback_summary_reads_and_aggregates` e substituir por:

```python
@pytest.mark.asyncio
async def test_feedback_summary_reads_and_aggregates(session):
    aid = uuid.uuid4()
    await _seed_feedback(session, aid, rating=5, made_sense=True, comment="bom", workout_type="ENDURANCE")
    await _seed_feedback(session, aid, rating=3, made_sense=False, comment="puxado", workout_type="VO2MAX")
    text, stats = await feedback_summary(session, _ctx(aid), aid)
    assert stats["count"] == 2
    assert stats["weighted"] is True       # prova que as_of foi injetado e a média é ponderada
    assert stats["half_life_days"] == 30
    assert stats["by_workout_type"]["VO2MAX"]["count"] == 1
    assert "Feedback recente (2 avaliações" in text
    assert "bom" in text or "puxado" in text
```

Os testes `test_feedback_summary_empty_is_nd` e `test_feedback_summary_isolated_per_athlete` ficam como estão.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_feedback_context.py -v"`
Expected: FAIL — `TypeError: summarize() missing 1 required keyword-only argument: 'as_of'` (ou `_rate()` argument) nos testes que ainda batem no código antigo

- [ ] **Step 3: Make `_rate` weighted**

Em `backend/app/services/ai/feedback_context.py`, substituir a função `_rate` inteira:

```python
def _rate(group: list["FeedbackItem"]) -> dict:
    n = len(group)
    avg = round(sum(i.rating for i in group) / n, 1)
    answered = [i.made_sense for i in group if i.made_sense is not None]
    pct = round(100 * sum(1 for m in answered if m) / len(answered)) if answered else None
    return {"count": n, "avg_rating": avg, "made_sense_pct": pct}
```

por:

```python
def _rate(group: list["FeedbackItem"], as_of: date) -> dict:
    n = len(group)
    weights = [_recency_weight(i.when, as_of) for i in group]
    wsum = sum(weights)
    avg = round(sum(w * i.rating for w, i in zip(weights, group)) / wsum, 1)
    answered = [(w, i.made_sense) for w, i in zip(weights, group) if i.made_sense is not None]
    if answered:
        den = sum(w for w, _ in answered)
        num = sum(w for w, m in answered if m)
        pct = round(100 * num / den)
    else:
        pct = None
    return {"count": n, "avg_rating": avg, "made_sense_pct": pct}
```

- [ ] **Step 4: Thread `as_of` through `summarize` + transparency marks**

Em `summarize`, mudar a assinatura e as chamadas de `_rate`, adicionar as marcas nos stats e relabelar o head.

Localizar a assinatura:

```python
def summarize(items: list[FeedbackItem], comment_limit: int = _DEFAULT_COMMENT_LIMIT) -> tuple[str, dict]:
    """Aggregate feedback (most-recent-first) into (pt-BR text, stats) por tipo de treino. ('n/d', {}) when empty."""
```

Trocar por:

```python
def summarize(items: list[FeedbackItem], comment_limit: int = _DEFAULT_COMMENT_LIMIT, *, as_of: date) -> tuple[str, dict]:
    """Aggregate feedback (most-recent-first) into (pt-BR text, stats) por tipo de treino,
    ponderado por recência (decay exponencial, meia-vida _HALF_LIFE_DAYS). ('n/d', {}) when empty."""
```

Localizar:

```python
    overall = _rate(items)
    by_workout_type: dict[str, dict] = {}
    grouped: dict[str, list[FeedbackItem]] = {}
    for i in items:
        grouped.setdefault(i.workout_type or "—", []).append(i)
    for wtype, group in grouped.items():
        by_workout_type[wtype] = _rate(group)
```

Trocar por:

```python
    overall = _rate(items, as_of)
    by_workout_type: dict[str, dict] = {}
    grouped: dict[str, list[FeedbackItem]] = {}
    for i in items:
        grouped.setdefault(i.workout_type or "—", []).append(i)
    for wtype, group in grouped.items():
        by_workout_type[wtype] = _rate(group, as_of)
```

Localizar:

```python
    stats = {**overall, "by_workout_type": by_workout_type}

    head = f"Feedback recente ({overall['count']} avaliações, nota média {overall['avg_rating']}"
```

Trocar por:

```python
    stats = {**overall, "by_workout_type": by_workout_type,
             "weighted": True, "half_life_days": _HALF_LIFE_DAYS}

    head = f"Feedback recente ({overall['count']} avaliações, nota média ponderada por recência {overall['avg_rating']}"
```

- [ ] **Step 5: Inject `as_of` in `feedback_summary`**

Em `feedback_summary`, localizar:

```python
    ctx.assert_can_access(athlete_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
```

Trocar por:

```python
    ctx.assert_can_access(athlete_id)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
```

E localizar a última linha:

```python
    return summarize(items, comment_limit)
```

Trocar por:

```python
    return summarize(items, comment_limit, as_of=now.date())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_feedback_context.py -v"`
Expected: PASS (todos — unit de peso, ponderação, mesma-idade, marcas, async)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/ai/feedback_context.py backend/app/tests/test_ai/test_feedback_context.py
git commit -m "feat(ai): media de feedback ponderada por recencia + marcas de transparencia"
```

---

### Task 3: Label do frontend reflete a ponderação

**Files:**
- Modify: `frontend/intelligence_view.py` (`feedback_line`, ~linha 60-61)
- Test: `frontend/test_intelligence_view.py` (asserir o novo label)

**Interfaces:**
- Consumes: stats com `avg_rating` (agora ponderado) — `feedback_line` já lê isso; nenhuma dependência nova.
- Produces: caption com "nota média ponderada {avg}".

- [ ] **Step 1: Update the test**

Em `frontend/test_intelligence_view.py`, localizar `test_feedback_line_renders_when_count_positive`:

```python
def test_feedback_line_renders_when_count_positive():
    from intelligence_view import feedback_line
    out = feedback_line({"count": 4, "avg_rating": 4.2, "made_sense_pct": 88})
    assert "4" in out and "4.2" in out and "88%" in out
    assert "avalia" in out.lower()
```

Trocar por:

```python
def test_feedback_line_renders_when_count_positive():
    from intelligence_view import feedback_line
    out = feedback_line({"count": 4, "avg_rating": 4.2, "made_sense_pct": 88})
    assert "4" in out and "4.2" in out and "88%" in out
    assert "avalia" in out.lower()
    assert "ponderada" in out.lower()  # label reflete o decay por recência
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest test_intelligence_view.py -k feedback_line -v"`
Expected: FAIL — `assert "ponderada" in out.lower()` (label ainda diz só "nota média")

- [ ] **Step 3: Update the label**

Em `frontend/intelligence_view.py`, localizar:

```python
    if avg is not None:
        parts += f" — nota média {avg}"
```

Trocar por:

```python
    if avg is not None:
        parts += f" — nota média ponderada {avg}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest -q"`
Expected: PASS (suíte de frontend verde, incl. o `feedback_line` atualizado e o teste sem made_sense que checa "3.5")

- [ ] **Step 5: Commit**

```bash
git add frontend/intelligence_view.py frontend/test_intelligence_view.py
git commit -m "feat(frontend): label 'nota média ponderada' no painel de feedback"
```

---

### Task 4: Regressão + suíte completa

**Files:**
- Test: `backend/app/tests/` (suíte inteira) + frontend

**Interfaces:**
- Consumes: tudo das Tasks 1-3.
- Produces: confirmação de que nenhum chamador de `summarize`/`_rate` ficou para trás e que a suíte está verde.

- [ ] **Step 1: Grep por chamadores remanescentes de `summarize`/`_rate`**

Usar o Grep tool: procurar `summarize(` e `_rate(` em `backend/app`.
Expected: o único `summarize(plan)` em `test_planning/test_periodization.py` é a função homônima do domínio de periodização (NÃO a de feedback) — confirmar que não foi tocada e que não há nenhum chamador de `feedback_context.summarize`/`_rate` sem `as_of`.

- [ ] **Step 2: Run the AI suite + day-adjustment (signals carregam feedback ponderado)**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai app/tests/test_api/test_day_adjustment.py -v"`
Expected: PASS (0 failures)

- [ ] **Step 3: Run the full backend suite**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest -q"`
Expected: exit 0. Anotar o resumo de warnings (esperado: apenas o `passlib/crypt` pré-existente).

- [ ] **Step 4: Run the full frontend suite**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest -q"`
Expected: PASS.

- [ ] **Step 5: Commit (se houver ajuste residual)**

Se o Step 1-4 expuser algum chamador esquecido, corrigir mínimo e:

```bash
git add -A
git commit -m "test(ai): alinha chamadores remanescentes a summarize(as_of)"
```

Se nada extra for necessário, pular este commit.

---

## Self-Review

**Spec coverage:**
- `_recency_weight` (0.5^(idade/30), clamp) → Task 1 ✓
- `_rate` pondera avg_rating + made_sense_pct, count cru → Task 2 Step 3 ✓
- `summarize(as_of)` + stats `weighted`/`half_life_days` + head relabel → Task 2 Steps 4 ✓
- Pureza (as_of injetado, sem now() interno) → Task 2 Step 5 (`feedback_summary` passa `now.date()`) ✓
- Frontend label → Task 3 ✓
- Janela 90d / caso vazio inalterados → Task 2 (não tocados; `test_summarize_empty_is_nd` cobre) ✓
- Mesma idade == média simples → Task 2 `test_summarize_same_age_equals_simple_mean` ✓
- Buckets por tipo herdam decay → Task 2 (via `_rate(group, as_of)`) ✓
- Não tocar `summarize` de periodização → Global Constraints + Task 4 Step 1 ✓
- Critérios de aceite 1-5 → Tasks 2 (math+marcas), 3 (label), 4 (suíte) ✓

**Placeholder scan:** sem TBD/TODO; todo passo de código mostra código exato. ✓

**Type consistency:** `_recency_weight(when: date, as_of: date) -> float` idêntico entre Task 1 def e uso em Task 2; `_rate(group, as_of)` consistente entre def e os dois call-sites em `summarize`; `summarize(items, comment_limit, *, as_of)` consistente entre def, `feedback_summary` e todos os testes; chaves de stats (`weighted`, `half_life_days`, `avg_rating`, `made_sense_pct`, `count`, `by_workout_type`) consistentes entre `_rate`/`summarize` e asserts. ✓

**Cálculo verificado (Task 2 test):** com `_AS_OF=2026-06-20`, itens (5@06-20 w1.0, 3@06-12 w≈0.831, 4@06-05 w≈0.707): avg ponderada = (5·1.0+3·0.831+4·0.707)/(1.0+0.831+0.707) ≈ 4.07 → 4.1; made_sense ponderado True(1.0+0.707)/(1.0+0.831+0.707) ≈ 67%; VO2MAX bucket (3@.831,4@.707) = (3·.831+4·.707)/(.831+.707) ≈ 3.46 → 3.5. Todos batem com os asserts. ✓
