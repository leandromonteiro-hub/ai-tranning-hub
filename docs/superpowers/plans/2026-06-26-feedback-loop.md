# Feedback loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar o ciclo de aprendizado — resumir o feedback do atleta e injetá-lo no prompt do LLM (recomendação diária e ajuste do dia), com transparência no painel "🔍 Baseado em".

**Architecture:** Novo `feedback_context` (helper puro `summarize` + função `feedback_summary` que lê o DB tenant-scoped) produz `(texto, stats)`. O texto vira a seção `{feedback}` do prompt (template `daily_workout` v3→v4, versionado). Ambos os fluxos do recommender passam o texto ao render e anexam `stats` em `payload.signals["feedback"]`. O frontend mostra uma linha de transparência quando `count>0`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Pydantic v2, pytest/pytest-asyncio (backend); Streamlit + pytest (frontend).

## Global Constraints

- Código em inglês; texto voltado ao atleta em PT-BR.
- Mecanismo é APENAS contexto no prompt (sem viés determinístico, sem fine-tuning). O feedback NUNCA sobrepõe os guardrails de segurança; nada de promessa de resultados.
- Resumo degrada para `("n/d", {})` quando não há feedback.
- Agregação por **bloco** (`payload.signals.block`), não por tipo de treino. Bloco ausente → `"—"`.
- Defaults documentados no módulo: `window_days=90`, `comment_limit=5`.
- Multi-tenant: leitura escopada por `athlete_id`/`ctx`; feedback de um atleta nunca entra no resumo de outro (provar A≠B).
- Helpers de resumo/render devem ser PUROS (sem I/O / sem `streamlit` no topo do módulo) para teste em container slim.
- Versionamento de template: `ACTIVE_TEMPLATES["daily_workout"]` sobe para versão 4; `ensure_templates` é idempotente por hash.
- TDD: teste falhando → mínimo p/ passar → commit. Commits frequentes.

**Comandos de teste:**
- Backend (um arquivo): `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -v"`
- Frontend: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest -q"`

---

## Mapa de arquivos

- Criar: `backend/app/services/ai/feedback_context.py` — `FeedbackItem`, `summarize` (puro), `feedback_summary` (DB)
- Modificar: `backend/app/services/ai/prompts.py` — seção `{feedback}` + `render_daily_workout(feedback=)` + v4
- Modificar: `backend/app/services/ai/recommender.py` — wiring em `generate_recommendation` e `generate_day_adjustment`
- Modificar: `frontend/intelligence_view.py` — `feedback_line(stats)` (puro)
- Modificar: `frontend/app.py` — render da linha no painel "Baseado em" + preview do ajuste
- Testes: `backend/app/tests/test_ai/test_feedback_context.py`, `.../test_prompts.py`, `.../test_signals.py` (ou um novo `test_feedback_wiring.py`), `frontend/test_intelligence_view.py`

---

## Task 1: `feedback_context.summarize` — agregação pura

**Files:**
- Create: `backend/app/services/ai/feedback_context.py`
- Test: `backend/app/tests/test_ai/test_feedback_context.py`

**Interfaces:**
- Produces:
  - `@dataclass FeedbackItem(rating: int, made_sense: bool | None, comment: str | None, block: str | None, when: date)`
  - `summarize(items: list[FeedbackItem], comment_limit: int = 5) -> tuple[str, dict]` — `items` em ordem do mais recente para o mais antigo. Retorna `(texto_pt_br, stats)`; `("n/d", {})` quando vazio. `stats = {"count", "avg_rating", "made_sense_pct" (int|None), "by_block": {bloco: {"count","avg_rating","made_sense_pct"}}}`.

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from app.services.ai.feedback_context import FeedbackItem, summarize


def _items():
    # mais recente primeiro
    return [
        FeedbackItem(5, True, "perfeito", "BASE", date(2026, 6, 20)),
        FeedbackItem(3, False, "muito puxado no fim", "BUILD", date(2026, 6, 12)),
        FeedbackItem(4, True, None, "BUILD", date(2026, 6, 5)),
    ]


def test_summarize_aggregates_overall_and_by_block():
    text, stats = summarize(_items())
    assert stats["count"] == 3
    assert stats["avg_rating"] == 4.0
    assert stats["made_sense_pct"] == 67  # 2 de 3 made_sense responderam, 2 True -> 67%
    assert stats["by_block"]["BUILD"]["count"] == 2
    assert stats["by_block"]["BUILD"]["avg_rating"] == 3.5
    assert "Feedback recente (3 avaliações, nota média 4.0" in text
    assert "Por bloco:" in text


def test_summarize_includes_recent_comments_with_label():
    text, _ = summarize(_items(), comment_limit=5)
    assert "[2026-06-20 · BASE] perfeito" in text
    assert "[2026-06-12 · BUILD] muito puxado no fim" in text


def test_summarize_respects_comment_limit_most_recent_first():
    text, _ = summarize(_items(), comment_limit=1)
    assert "perfeito" in text          # mais recente
    assert "muito puxado" not in text  # cortado pelo limite


def test_summarize_empty_is_nd():
    assert summarize([]) == ("n/d", {})


def test_summarize_block_none_groups_under_dash():
    text, stats = summarize([FeedbackItem(4, None, None, None, date(2026, 6, 1))])
    assert stats["by_block"]["—"]["count"] == 1
    assert stats["made_sense_pct"] is None   # ninguém respondeu made_sense
    assert "Por bloco:" not in text          # "—" não vira recorte textual
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_feedback_context.py -v"`
Expected: FAIL — `ModuleNotFoundError: app.services.ai.feedback_context`.

- [ ] **Step 3: Implement `FeedbackItem` + `summarize`**

```python
"""Summarise athlete feedback for the recommendation prompt + transparency.

Mirrors profile_context.twin_seed_summary: aggregates recent feedback (rating,
made_sense, comments) into a compact PT-BR string injected as the prompt's
{feedback} section, plus a stats dict surfaced in the "Baseado em" panel. Pure
aggregation (summarize) is separated from the DB read (feedback_summary)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.models.ai import AiRecommendation, AiRecommendationFeedback

_DEFAULT_WINDOW_DAYS = 90
_DEFAULT_COMMENT_LIMIT = 5


@dataclass
class FeedbackItem:
    rating: int
    made_sense: bool | None
    comment: str | None
    block: str | None
    when: date


def _rate(group: list["FeedbackItem"]) -> dict:
    n = len(group)
    avg = round(sum(i.rating for i in group) / n, 1)
    answered = [i.made_sense for i in group if i.made_sense is not None]
    pct = round(100 * sum(1 for m in answered if m) / len(answered)) if answered else None
    return {"count": n, "avg_rating": avg, "made_sense_pct": pct}


def summarize(items: list[FeedbackItem], comment_limit: int = _DEFAULT_COMMENT_LIMIT) -> tuple[str, dict]:
    """Aggregate feedback (most-recent-first) into (pt-BR text, stats). ('n/d', {}) when empty."""
    if not items:
        return "n/d", {}

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

    head = f"Feedback recente ({overall['count']} avaliações, nota média {overall['avg_rating']}"
    if overall["made_sense_pct"] is not None:
        head += f", fez sentido {overall['made_sense_pct']}%"
    head += ")"
    parts = [head]

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
    if comments:
        parts.append("Comentários: " + "; ".join(comments))

    return " · ".join(parts), stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: mesmo comando do Step 2.
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/feedback_context.py backend/app/tests/test_ai/test_feedback_context.py
git commit -m "feat(ai): feedback_context.summarize — agrega feedback (geral + por bloco + comentarios)"
```

---

## Task 2: `feedback_summary` — leitura tenant-scoped do DB

**Files:**
- Modify: `backend/app/services/ai/feedback_context.py`
- Test: `backend/app/tests/test_ai/test_feedback_context.py`

**Interfaces:**
- Consumes: `summarize`, `FeedbackItem` (Task 1); `AiRecommendation`, `AiRecommendationFeedback` (DB models, com `created_at`/`deleted_at` de `Base`).
- Produces: `async def feedback_summary(session, ctx, athlete_id, *, window_days=90, comment_limit=5) -> tuple[str, dict]`.

- [ ] **Step 1: Write the failing test**

```python
import uuid
import pytest
from datetime import date

from app.core.tenant import TenantContext
from app.models.ai import AiRecommendation, AiRecommendationFeedback
from app.models.enums import RecommendationDecision, RiskLevel
from app.services.ai.feedback_context import feedback_summary

pytestmark = pytest.mark.asyncio


def _ctx(aid):
    from app.models.enums import Role
    return TenantContext(athlete_id=aid, tenant_id="t", role=Role.ATHLETE)


async def _seed_feedback(session, aid, *, rating, made_sense, comment, block):
    rec = AiRecommendation(
        athlete_id=aid, target_date=date(2026, 6, 20), kind="daily_workout",
        summary="s", risk_level=RiskLevel.LOW, decision=RecommendationDecision.PENDING,
        payload={"signals": {"block": block}},
    )
    session.add(rec)
    await session.flush()
    session.add(AiRecommendationFeedback(
        athlete_id=aid, recommendation_id=rec.id, rating=rating,
        made_sense=made_sense, comment=comment,
    ))
    await session.flush()


async def test_feedback_summary_reads_and_aggregates(session):
    aid = uuid.uuid4()
    await _seed_feedback(session, aid, rating=5, made_sense=True, comment="bom", block="BASE")
    await _seed_feedback(session, aid, rating=3, made_sense=False, comment="puxado", block="BUILD")
    text, stats = await feedback_summary(session, _ctx(aid), aid)
    assert stats["count"] == 2
    assert "Feedback recente (2 avaliações" in text
    assert "bom" in text or "puxado" in text


async def test_feedback_summary_empty_is_nd(session):
    aid = uuid.uuid4()
    assert await feedback_summary(session, _ctx(aid), aid) == ("n/d", {})


async def test_feedback_summary_isolated_per_athlete(session):
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed_feedback(session, a, rating=5, made_sense=True, comment="de A", block="BASE")
    text_b, stats_b = await feedback_summary(session, _ctx(b), b)
    assert (text_b, stats_b) == ("n/d", {})  # B não vê o feedback de A
```

(Usa a fixture `session` do `conftest`. Se `TenantContext` exigir outros campos, espelhe `ctx_for` do conftest.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_feedback_context.py -k feedback_summary -v"`
Expected: FAIL — `ImportError: cannot import name 'feedback_summary'`.

- [ ] **Step 3: Implement `feedback_summary`**

Acrescentar ao final de `feedback_context.py`:

```python
async def feedback_summary(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    comment_limit: int = _DEFAULT_COMMENT_LIMIT,
) -> tuple[str, dict]:
    """Read recent feedback for one athlete (tenant-scoped) and summarise it."""
    ctx.assert_can_access(athlete_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    stmt = (
        select(AiRecommendationFeedback, AiRecommendation)
        .join(AiRecommendation,
              AiRecommendationFeedback.recommendation_id == AiRecommendation.id)
        .where(
            AiRecommendationFeedback.athlete_id == athlete_id,
            AiRecommendationFeedback.deleted_at.is_(None),
            AiRecommendationFeedback.created_at >= cutoff,
        )
        .order_by(AiRecommendationFeedback.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    items: list[FeedbackItem] = []
    for fb, rec in rows:
        block = ((rec.payload or {}).get("signals") or {}).get("block")
        when = (fb.created_at or datetime.now(timezone.utc)).date()
        items.append(FeedbackItem(
            rating=fb.rating, made_sense=fb.made_sense,
            comment=fb.comment, block=block, when=when,
        ))
    return summarize(items, comment_limit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: mesmo comando do Step 2.
Expected: PASS (3 testes; isolamento A≠B confirmado).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/feedback_context.py backend/app/tests/test_ai/test_feedback_context.py
git commit -m "feat(ai): feedback_summary — leitura tenant-scoped do feedback recente"
```

---

## Task 3: Seção `{feedback}` no prompt + template v4

**Files:**
- Modify: `backend/app/services/ai/prompts.py`
- Test: `backend/app/tests/test_ai/test_prompts.py`

**Interfaces:**
- Produces: `render_daily_workout(..., feedback: str = "n/d")`; `ACTIVE_TEMPLATES["daily_workout"] == (4, DAILY_WORKOUT_TEMPLATE)`.

- [ ] **Step 1: Write the failing test**

```python
def test_render_includes_feedback_section():
    from app.services.ai import prompts
    out = prompts.render_daily_workout(
        twin="T", safety="S", evidence="E", knowledge="K", question="q",
        feedback="Feedback recente (3 avaliações, nota média 4.0)",
    )
    assert "Feedback recente (3 avaliações, nota média 4.0)" in out
    assert "{feedback}" not in out          # placeholder preenchido
    assert prompts.ACTIVE_TEMPLATES["daily_workout"][0] == 4


def test_render_feedback_defaults_to_nd():
    from app.services.ai import prompts
    out = prompts.render_daily_workout(twin="T", safety="S", evidence="E",
                                       knowledge="K", question="q")
    assert "{feedback}" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_prompts.py -k feedback -v"`
Expected: FAIL (`feedback` não é parâmetro; versão é 3).

- [ ] **Step 3: Add the section, param and bump the version**

Em `prompts.py`, inserir uma seção no `DAILY_WORKOUT_TEMPLATE` logo ANTES de `Athlete question / request:`:

```
Athlete feedback on recent recommendations (respect what worked; adjust what
was rated poorly — never promise results, never override the safety guardrail):
{feedback}

```

Atualizar `render_daily_workout`:

```python
def render_daily_workout(
    twin: str, safety: str, evidence: str, knowledge: str, question: str,
    profile: str = "n/d", methodology: str = "n/d", feedback: str = "n/d",
) -> str:
    return DAILY_WORKOUT_TEMPLATE.format(
        profile=profile, methodology=methodology, twin=twin, safety=safety,
        evidence=evidence, knowledge=knowledge, feedback=feedback,
        question=question or "Recommend today's workout.",
    )
```

Bump da versão:

```python
ACTIVE_TEMPLATES = {
    "daily_workout": (4, DAILY_WORKOUT_TEMPLATE),
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_prompts.py -q"`
Expected: PASS (incluindo os testes de metodologia existentes — eles não passam `feedback`, então o default "n/d" preenche o placeholder; confirme que continuam verdes).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/prompts.py backend/app/tests/test_ai/test_prompts.py
git commit -m "feat(ai): seção {feedback} no prompt daily_workout (v4)"
```

---

## Task 4: Wiring no recommender (ambos os fluxos)

**Files:**
- Modify: `backend/app/services/ai/recommender.py`
- Test: `backend/app/tests/test_ai/test_feedback_wiring.py` (criar)

**Interfaces:**
- Consumes: `feedback_context.feedback_summary` (Task 2); `prompts.render_daily_workout(feedback=)` (Task 3); `_signals(snapshot, methodology, block, ftp_watts)` (existente, retorna dict).
- Produces: em `generate_recommendation` e `generate_day_adjustment`, o prompt inclui o feedback e `rec.payload["signals"]["feedback"]` = stats.

- [ ] **Step 1: Write the failing test**

```python
import uuid
import pytest
from datetime import date

from app.models.ai import AiRecommendation, AiRecommendationFeedback
from app.models.enums import RecommendationDecision, RiskLevel
from app.models.metrics import FtpHistory
from app.services.ai.recommender import generate_recommendation
from app.tests.conftest import ctx_for

pytestmark = pytest.mark.asyncio


async def test_recommendation_payload_carries_feedback_stats(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    session.add(FtpHistory(athlete_id=a.id, created_by=a.id, ftp_watts=240.0,
                           valid_from=date(2026, 1, 1)))
    prior = AiRecommendation(
        athlete_id=a.id, target_date=date(2026, 6, 1), kind="daily_workout",
        summary="s", risk_level=RiskLevel.LOW, decision=RecommendationDecision.PENDING,
        payload={"signals": {"block": "BASE"}},
    )
    session.add(prior)
    await session.flush()
    session.add(AiRecommendationFeedback(athlete_id=a.id, recommendation_id=prior.id,
                                         rating=5, made_sense=True, comment="ótimo"))
    await session.flush()

    rec = await generate_recommendation(session, ctx, a.id,
                                        target_date=date(2026, 6, 23), kind="daily_workout")
    fb = (rec.payload or {}).get("signals", {}).get("feedback")
    assert fb is not None
    assert fb["count"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_feedback_wiring.py -v"`
Expected: FAIL — `signals.feedback` é `None` (não populado ainda).

- [ ] **Step 3: Wire feedback into both flows**

No topo de `recommender.py`, adicionar `feedback_context` ao import existente:
```python
from app.services.ai import evidence_builder, feedback_context, profile_context, prompt_store, prompts, rag
```

Em `generate_recommendation`, ANTES do bloco `prompt = prompts.render_daily_workout(...)`:
```python
    feedback_text, feedback_stats = await feedback_context.feedback_summary(
        session, ctx, athlete_id
    )
```
Adicionar `feedback=feedback_text,` aos argumentos de `render_daily_workout(...)`.
Trocar a construção dos signals no payload — em vez de `"signals": _signals(...)`, fazer antes do `AiRecommendation(...)`:
```python
    signals = _signals(twin.snapshot, methodology, block, ftp_watts)
    signals["feedback"] = feedback_stats
```
e no payload usar `"signals": signals,`.

Repetir EXATAMENTE o mesmo em `generate_day_adjustment` (computar `feedback_text, feedback_stats`, passar `feedback=feedback_text` ao render, montar `signals` + `signals["feedback"] = feedback_stats`, usar no payload).

- [ ] **Step 4: Run test to verify it passes**

Run: mesmo comando do Step 2.
Expected: PASS.

- [ ] **Step 5: Run the recommender/day-adjustment suites for regressions**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_workout app/tests/test_ai -q"`
Expected: verde (os fluxos existentes continuam; `_signals` inalterado, só estendido o dict no call site).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ai/recommender.py backend/app/tests/test_ai/test_feedback_wiring.py
git commit -m "feat(ai): injeta feedback no prompt + signals (recomendação diária e ajuste do dia)"
```

---

## Task 5: Transparência no frontend

**Files:**
- Modify: `frontend/intelligence_view.py`
- Modify: `frontend/app.py` (`recommendations_tab` painel "🔍 Baseado em"; `_render_day_detail` preview do ajuste)
- Test: `frontend/test_intelligence_view.py`

**Interfaces:**
- Consumes: `signals["feedback"]` = `{count, avg_rating, made_sense_pct, by_block}` (Task 4).
- Produces: `intelligence_view.feedback_line(stats: dict | None) -> str` — frase pt-BR, `""` quando vazio/`count==0`.

- [ ] **Step 1: Write the failing test**

Em `frontend/test_intelligence_view.py`, adicionar ao import `feedback_line` e:

```python
def test_feedback_line_renders_when_count_positive():
    from intelligence_view import feedback_line
    out = feedback_line({"count": 4, "avg_rating": 4.2, "made_sense_pct": 88})
    assert "4" in out and "4.2" in out and "88%" in out
    assert "avalia" in out.lower()


def test_feedback_line_empty_when_no_feedback():
    from intelligence_view import feedback_line
    assert feedback_line(None) == ""
    assert feedback_line({}) == ""
    assert feedback_line({"count": 0}) == ""


def test_feedback_line_without_made_sense():
    from intelligence_view import feedback_line
    out = feedback_line({"count": 2, "avg_rating": 3.5, "made_sense_pct": None})
    assert "3.5" in out
    assert "%" not in out  # sem o trecho de "fez sentido"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest test_intelligence_view.py -k feedback -q"`
Expected: FAIL (`feedback_line` não existe).

- [ ] **Step 3: Implement `feedback_line`**

Em `frontend/intelligence_view.py` (junto aos outros helpers puros):

```python
def feedback_line(stats: dict | None) -> str:
    """One-line transparency note that recent feedback informed the suggestion.
    Empty string when there is no feedback."""
    if not stats or not stats.get("count"):
        return ""
    n = stats["count"]
    avg = stats.get("avg_rating")
    parts = f"📝 Considerou suas últimas {n} avaliações"
    if avg is not None:
        parts += f" — nota média {avg}"
    pct = stats.get("made_sense_pct")
    if pct is not None:
        parts += f" · fez sentido {pct}%"
    return parts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: mesmo comando do Step 2, depois a suíte inteira: `... python -m pytest -q`.
Expected: PASS (novos + existentes verdes).

- [ ] **Step 5: Render no app.py (painel "Baseado em" + preview do ajuste)**

Em `frontend/app.py`, no painel "🔍 Baseado em" de `recommendations_tab` (dentro do `with st.expander("🔍 Baseado em ...")`), após as métricas de forma, adicionar:
```python
                fb_line = iv.feedback_line(sig.get("feedback"))
                if fb_line:
                    st.caption(fb_line)
```
(`iv` é o alias de `intelligence_view` já importado; `sig` é `(rec.get("payload") or {}).get("signals") or {}`.)

No preview do ajuste em `_render_day_detail` (onde `preview` é mostrado), após a linha de risco/resumo, adicionar:
```python
                fb_line = iv.feedback_line(((pl.get("signals")) or {}).get("feedback"))
                if fb_line:
                    st.caption(fb_line)
```
(`pl` é `preview.get("payload") or {}`.)

Rodar o compile check do app.py:
`docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "cd /f && python -m py_compile app.py intelligence_view.py && echo COMPILE_OK"`

- [ ] **Step 6: Commit**

```bash
git add frontend/intelligence_view.py frontend/app.py frontend/test_intelligence_view.py
git commit -m "feat(frontend): linha de transparência do feedback no painel Baseado em + preview do ajuste"
```

---

## Task 6: Verificação ponta a ponta

**Files:** nenhum (operacional).

- [ ] **Step 1: Suítes completas**

```bash
docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests -q"
docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest -q"
```
Expected: backend exit 0 (só o warning pré-existente passlib/crypt); frontend verde.

- [ ] **Step 2: Smoke e2e (opcional, stack vivo)**

Subir/rebuild a api (`docker compose up -d --build api`), logar como leandro, enviar um feedback numa recomendação (`POST /feedback/{rec_id}`), gerar nova recomendação e confirmar `payload.signals.feedback.count >= 1` e que o prompt logado contém "Feedback recente". Registrar evidência.

- [ ] **Step 3: Atualizar o ledger**

Anotar o estado final em `.superpowers/sdd/progress.md`.

---

## Self-Review (autor do plano)

**Cobertura do spec:**
- feedback_context (summarize puro) → Task 1 ✓; (feedback_summary DB + tenant A≠B) → Task 2 ✓
- prompt {feedback} + v4 → Task 3 ✓
- recommender ambos os fluxos (prompt + signals) → Task 4 ✓
- transparência frontend (painel + preview) → Task 5 ✓
- testes incl. isolamento, fallback "n/d", defaults → Tasks 1/2/5 ✓
- verificação → Task 6 ✓
- Não-objetivos respeitados (sem viés determinístico, sem por-tipo-de-treino, sem fine-tuning).

**Consistência de tipos:** `summarize(items, comment_limit)->(str,dict)` e `feedback_summary(...)->(str,dict)` iguais nas Tasks 1/2/4. `stats` keys (`count`, `avg_rating`, `made_sense_pct`, `by_block`) consistentes entre Tasks 1/4/5. `feedback_line(stats)->str` igual nas Tasks 5. `render_daily_workout(..., feedback=)` igual nas Tasks 3/4.

**Riscos sinalizados:** (a) `TenantContext` nos testes — espelhar `ctx_for`/conftest se exigir campos; (b) `created_at` é default do DB (Base) — feedback semeado cai na janela de 90 dias automaticamente; (c) confirmar o ponto exato de inserção no painel "Baseado em" lendo o `recommendations_tab` antes de editar.
