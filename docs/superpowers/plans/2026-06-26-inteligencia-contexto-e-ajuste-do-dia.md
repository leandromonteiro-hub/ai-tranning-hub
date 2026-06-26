# Inteligência com contexto completo + Ajuste do dia — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar o vão entre o treino planejado e a IA — enriquecer o contexto da inteligência (metodologia do treinador + base de conhecimento) e permitir que a IA ajuste o treino planejado do dia ao estado de forma atual, com override reversível no calendário.

**Architecture:** Quatro partes num spec/branch único. (1a) `_build_twin_seed` passa a gravar taper/provas/termos do treinador/periodização e `twin_seed_summary` os injeta no prompt. (1b) `ensure_knowledge()` semeia a base RAG no startup. (1c) achados dos artigos viram documentos curados recuperáveis. (2) `workout_adjuster` (puro) transforma o treino planejado por faixa de risco; `generate_day_adjustment` orquestra twin+guardrails+LLM; coluna `adjustment` (jsonb) guarda o override reversível; rotas e UI no calendário.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, Pydantic v2, pytest/pytest-asyncio (backend); Streamlit + pytest (frontend). LLM via `LlmClient` (claude-opus).

## Global Constraints

- Código em inglês; texto voltado ao atleta em PT-BR.
- Migrações **aditivas**; usar `from sqlalchemy.dialects.postgresql import UUID as PG_UUID` com `PG_UUID(as_uuid=True)` para colunas/FK UUID (convenção do projeto, ver `0007`).
- Multi-tenant: toda query/rota nova passa por `get_tenant` / `TenantContext`; provar isolamento A≠B onde aplicável.
- Funções de análise/render devem ser **puras** (sem I/O, sem `streamlit` no topo do módulo) para serem testáveis em container slim.
- Nada de promessa de resultados; separar dado real / inferido / conhecimento geral.
- Startup nunca quebra por seed (try/except + `log.warning`, igual a `ensure_prompt_templates`).
- TDD: teste falhando → mínimo p/ passar → commit. Commits frequentes.

**Comandos de teste:**
- Backend (um arquivo): `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -v"`
- Frontend: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest -q"`

---

## Mapa de arquivos

**Backend**
- Modificar: `backend/app/services/analysis/report_builder.py` — `_build_twin_seed` + `build_profile_report` (1a)
- Modificar: `backend/app/services/ai/profile_context.py` — `twin_seed_summary` (1a)
- Modificar: `backend/app/bootstrap.py` + `backend/app/main.py` — `ensure_knowledge()` (1b)
- Modificar: `backend/app/services/knowledge/document_loader.py` — `CURATED_DOCUMENTS` (1c)
- Criar: `backend/app/services/planning/workout_adjuster.py` — adjuster puro (2)
- Modificar: `backend/app/services/ai/recommender.py` — `generate_day_adjustment` (2)
- Modificar: `backend/app/models/workout.py` — `WorkoutPlanned.adjustment` (2)
- Criar: `backend/alembic/versions/0008_workout_planned_adjustment.py` (2)
- Modificar: `backend/app/schemas/planning.py` — `PlannedWorkoutRead.adjustment` (2)
- Modificar: `backend/app/api/routes/plans.py` — rotas adjust/apply/revert (2)

**Frontend**
- Modificar: `frontend/calendar_view.py` — `effective_workout` + selo "IA" (2)
- Modificar: `frontend/app.py` — painel de detalhe (botões) + valores efetivos no calendário (2)

**Testes**
- `backend/app/tests/test_analysis/test_report_builder.py` (ou arquivo existente equivalente) — 1a
- `backend/app/tests/test_ai/test_profile_context.py` — 1a
- `backend/app/tests/test_api/test_bootstrap_knowledge.py` — 1b/1c
- `backend/app/tests/test_planning/test_workout_adjuster.py` — 2
- `backend/app/tests/test_api/test_day_adjustment.py` — 2 (rotas)
- `frontend/test_calendar_view.py` — 2 (selo/efetivo)

> Antes de criar arquivos de teste, confirme o diretório existente correspondente (ex.: `ls backend/app/tests/test_analysis/`); se não existir, crie seguindo o padrão dos vizinhos.

---

## Task 1: `twin_seed` grava taper/provas/termos/periodização (1a)

**Files:**
- Modify: `backend/app/services/analysis/report_builder.py` (`_build_twin_seed` ~380-453; call site ~523; `build_profile_report` ~461)
- Test: `backend/app/tests/test_analysis/test_report_builder.py`

**Interfaces:**
- Consumes: `Race(date, name, evidence)`, `TaperWindow(race_date, ctl_start, ctl_race, atl_race, tsb_race, weekly_tss_trend, evidence)`, `Block(start, end, block_type, evidence)` de `app.services.analysis.methodology`; `comment_terms: list[tuple[str, int]]`.
- Produces: `twin_seed` dict ganha chaves `tapers: list[dict]`, `races: list[dict]`, `coach_terms: list[list]`, `periodization_summary: dict`. (Consumido pela Task 2.)

- [ ] **Step 1: Write the failing test**

Em `test_report_builder.py`, adicionar (ajuste imports/fixtures conforme os testes existentes do arquivo — eles já constroem os objetos de entrada de `build_profile_report`):

```python
def test_twin_seed_includes_methodology_signals():
    from datetime import date
    from app.services.analysis.methodology import Race, TaperWindow
    from app.services.analysis import report_builder as rb

    # Reusa o helper interno diretamente com objetos mínimos:
    races = [Race(date=date(2025, 5, 4), name="XCO Cup", evidence="keyword:xco")]
    tapers = [TaperWindow(race_date=date(2025, 5, 4), ctl_start=80.0, ctl_race=78.0,
                          atl_race=55.0, tsb_race=23.0,
                          weekly_tss_trend=[600.0, 450.0, 300.0],
                          evidence="CTL -2, TSB +23 no dia da prova")]
    comment_terms = [("sweet", 12), ("limiar", 9), ("z2", 7)]

    seed = rb._build_twin_seed_methodology(races, tapers, comment_terms,
                                           power_curve_bests={}, blocks=[])

    assert seed["races"][0]["name"] == "XCO Cup"
    assert seed["tapers"][0]["tsb_race"] == 23.0
    assert seed["tapers"][0]["weekly_tss_trend"] == [600.0, 450.0, 300.0]
    assert seed["coach_terms"][:1] == [["sweet", 12]]
    assert "n_blocks" in seed["periodization_summary"]
```

> Nota: introduzimos um helper puro `_build_twin_seed_methodology` para manter `_build_twin_seed` enxuto e o teste focado. Se preferir, teste via `_build_twin_seed` completo — mas o helper isola a lógica nova.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_analysis/test_report_builder.py::test_twin_seed_includes_methodology_signals -v"`
Expected: FAIL com `AttributeError: ... has no attribute '_build_twin_seed_methodology'`.

- [ ] **Step 3: Implement the helper + wire into `_build_twin_seed`**

Em `report_builder.py`, adicionar o helper e chamá-lo dentro de `_build_twin_seed`:

```python
def _build_twin_seed_methodology(
    races, tapers, comment_terms, power_curve_bests, blocks,
) -> dict:
    """Methodology signals for the twin_seed: races, taper strategy, coach
    terminology and a compact periodization pattern. Pure; no DB."""
    races_out = [
        {"date": _fmt_date_iso(r.date), "name": r.name, "evidence": r.evidence}
        for r in races
    ]
    tapers_out = [
        {
            "race_date": _fmt_date_iso(t.race_date),
            "ctl_start": round(t.ctl_start, 1),
            "ctl_race": round(t.ctl_race, 1),
            "atl_race": round(t.atl_race, 1),
            "tsb_race": round(t.tsb_race, 1),
            "weekly_tss_trend": [round(v, 1) for v in t.weekly_tss_trend],
            "evidence": t.evidence,
        }
        for t in tapers
    ]
    coach_terms = [[term, count] for term, count in comment_terms[:15]]

    # Periodização: só o que já é derivável de `blocks` (datas/tipos). Sem novo cálculo.
    durations = [(b.end - b.start).days + 1 for b in blocks]
    recovery_blocks = sum(1 for b in blocks if (b.block_type or "").lower() == "recovery")
    periodization_summary = {
        "n_blocks": len(blocks),
        "meso_length_days_typical": (
            round(sum(durations) / len(durations)) if durations else None
        ),
        "recovery_blocks": recovery_blocks,
    }
    return {
        "races": races_out,
        "tapers": tapers_out,
        "coach_terms": coach_terms,
        "periodization_summary": periodization_summary,
    }
```

Em `_build_twin_seed`, mudar a assinatura para receber `races`, `tapers`, `comment_terms` e mesclar:

```python
def _build_twin_seed(
    power_marks, ftp_timeline, intensity, blocks, modality, volume_trend,
    races, tapers, comment_terms,
) -> dict:
    ...  # (corpo existente que monta power_curve_bests, etc.)
    seed = {
        "power_curve_bests": power_curve_bests,
        "ftp_timeline": ftp_list,
        "intensity_split": intensity_split,
        "block_summary": block_summary,
        "best_marks": best_marks,
        "data_richness": data_richness,
    }
    seed.update(
        _build_twin_seed_methodology(
            races, tapers, comment_terms, power_curve_bests, blocks
        )
    )
    return seed
```

Atualizar a **chamada** em `build_profile_report` (~linha 523) para passar `races`, `tapers`, `comment_terms` (já presentes no escopo da função):

```python
    twin_seed = _build_twin_seed(
        power_marks, ftp_timeline, intensity, blocks, modality, volume_trend,
        races, tapers, comment_terms,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: mesmo comando do Step 2.
Expected: PASS.

- [ ] **Step 5: Run the report_builder suite to confirm no regressions**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_analysis/test_report_builder.py -q"`
Expected: tudo verde (testes existentes que chamam `_build_twin_seed`/`build_profile_report` continuam passando).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/analysis/report_builder.py backend/app/tests/test_analysis/test_report_builder.py
git commit -m "feat(analysis): twin_seed grava taper/provas/termos/periodização do treinador"
```

---

## Task 2: `twin_seed_summary` injeta os novos sinais no prompt (1a)

**Files:**
- Modify: `backend/app/services/ai/profile_context.py` (`twin_seed_summary` ~41-79)
- Test: `backend/app/tests/test_ai/test_profile_context.py`

**Interfaces:**
- Consumes: `twin_seed` com `tapers`, `races`, `coach_terms`, `periodization_summary` (Task 1).
- Produces: string multi-parte injetada como `{methodology}` em `recommender.py` (já consumido lá).

- [ ] **Step 1: Write the failing test**

```python
def test_twin_seed_summary_surfaces_taper_terms_periodization():
    from app.services.ai.profile_context import twin_seed_summary

    class _P:  # stub com só o atributo twin_seed
        twin_seed = {
            "tapers": [{"race_date": "2025-05-04", "tsb_race": 23.0,
                        "weekly_tss_trend": [600.0, 450.0, 300.0]}],
            "coach_terms": [["sweet", 12], ["limiar", 9]],
            "periodization_summary": {"n_blocks": 6, "meso_length_days_typical": 24,
                                      "recovery_blocks": 2},
        }

    out = twin_seed_summary(_P())
    assert "Taper" in out
    assert "sweet" in out
    assert "Periodização" in out


def test_twin_seed_summary_handles_missing_methodology():
    from app.services.ai.profile_context import twin_seed_summary

    class _P:
        twin_seed = {"intensity_split": {"z1_pct": 0.8, "z2_pct": 0.1, "z3_pct": 0.1,
                                         "label": "polarizado"}}

    out = twin_seed_summary(_P())
    assert "Taper" not in out  # sem dado de taper, não inventa a seção
    assert out != "n/d"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_profile_context.py -k twin_seed_summary -v"`
Expected: FAIL (asserts de Taper/sweet/Periodização não encontrados).

- [ ] **Step 3: Estender `twin_seed_summary`**

Acrescentar, antes do `return`, blocos que só aparecem quando há dado:

```python
    tapers = seed.get("tapers") or []
    if tapers:
        t0 = tapers[0]
        tsb = t0.get("tsb_race")
        trend = t0.get("weekly_tss_trend") or []
        drop = ""
        if len(trend) >= 2 and trend[0]:
            drop = f", volume ↓ ~{round((1 - trend[-1] / trend[0]) * 100)}%"
        parts.append(
            f"Taper típico (n={len(tapers)}): TSB ~{round(tsb) if tsb is not None else '—'} "
            f"no dia da prova{drop}"
        )

    terms = seed.get("coach_terms") or []
    if terms:
        names = ", ".join(t[0] for t in terms[:8])
        parts.append(f"Terminologia do treinador: {names}")

    per = seed.get("periodization_summary") or {}
    if per.get("n_blocks"):
        meso = per.get("meso_length_days_typical")
        rec = per.get("recovery_blocks")
        meso_txt = f", mesos ~{meso}d" if meso else ""
        rec_txt = f", {rec} blocos regen" if rec else ""
        parts.append(f"Periodização real ({per['n_blocks']} blocos{meso_txt}{rec_txt})")
```

(Mantém as `parts` já existentes — intensity_split, bests, etc. — e o `return " · ".join(parts) if parts else "n/d"`.)

- [ ] **Step 4: Run test to verify it passes**

Run: mesmo comando do Step 2.
Expected: PASS (ambos os testes).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/profile_context.py backend/app/tests/test_ai/test_profile_context.py
git commit -m "feat(ai): injeta taper, terminologia e periodização do treinador no prompt"
```

---

## Task 3: Auto-seed da base de conhecimento no startup (1b)

**Files:**
- Modify: `backend/app/bootstrap.py`
- Modify: `backend/app/main.py` (lifespan ~32-34)
- Test: `backend/app/tests/test_api/test_bootstrap_knowledge.py` (criar)

**Interfaces:**
- Consumes: `ingest_curated_knowledge(session) -> dict` (existente, idempotente por título).
- Produces: `ensure_knowledge() -> None` (chamada no lifespan).

- [ ] **Step 1: Write the failing test**

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.services.knowledge.knowledge_service import (
    ingest_curated_knowledge, knowledge_stats,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:",
                                 connect_args={"check_same_thread": False}, poolclass=StaticPool)
    # embeddings usa pgvector (não suportado no sqlite) → cria as outras tabelas
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


async def test_ingest_is_idempotent(maker):
    async with maker() as s:
        first = await ingest_curated_knowledge(s)
        await s.commit()
    async with maker() as s:
        second = await ingest_curated_knowledge(s)
        await s.commit()
        stats = await knowledge_stats(s)
    assert first["documents_created"] > 0
    assert second["documents_created"] == 0  # nada duplicado na 2ª passada
    assert stats["documents"] == first["documents_created"]
```

> A tabela `embeddings` depende de pgvector; o teste de idempotência roda sobre `knowledge_documents` (o skip por título acontece antes de criar embeddings). Se `ingest_curated_knowledge` falhar ao inserir embeddings no sqlite, envolva a verificação no teste com tabelas disponíveis — confirme o comportamento atual rodando o Step 2.

- [ ] **Step 2: Run test to verify it fails or reveals the embeddings constraint**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_bootstrap_knowledge.py -v"`
Expected: FAIL inicialmente porque o arquivo/funcão `ensure_knowledge` ainda não existe **ou** porque o insert de embeddings precisa de pgvector. Se for o segundo caso, ajuste o teste para criar a tabela `embeddings` via o tipo local de embeddings dos testes (ver `conftest`/`0003_local_embeddings_dim`) ou marque o assert de embeddings como dependente de pgvector. O assert central (idempotência de documentos) deve poder rodar.

- [ ] **Step 3: Adicionar `ensure_knowledge` no bootstrap**

Em `bootstrap.py`:

```python
async def ensure_knowledge() -> None:
    """Seed the global training-knowledge base so RAG is never empty.

    Idempotent (ingest skips documents whose title already exists). Never blocks
    startup — mirrors ensure_prompt_templates."""
    from app.services.knowledge.knowledge_service import ingest_curated_knowledge

    async with AsyncSessionLocal() as session:
        try:
            result = await ingest_curated_knowledge(session)
            await session.commit()
            log.info("knowledge_seeded", extra=result)
        except Exception:  # noqa: BLE001 — never block startup on this
            log.warning("knowledge_seed_failed")
```

- [ ] **Step 4: Wire into the lifespan**

Em `main.py`, importar e chamar após `ensure_prompt_templates()`:

```python
from app.bootstrap import (
    ensure_admin, ensure_knowledge, ensure_pgvector, ensure_prompt_templates,
)
...
    await ensure_pgvector()
    await ensure_admin()
    await ensure_prompt_templates()
    await ensure_knowledge()
```

- [ ] **Step 5: Run test to verify it passes**

Run: mesmo comando do Step 2.
Expected: PASS (idempotência confirmada).

- [ ] **Step 6: Commit**

```bash
git add backend/app/bootstrap.py backend/app/main.py backend/app/tests/test_api/test_bootstrap_knowledge.py
git commit -m "feat(knowledge): auto-seed da base RAG no startup (idempotente, não bloqueia)"
```

---

## Task 4: Ingerir achados dos artigos como documentos curados (1c)

**Files:**
- Modify: `backend/app/services/knowledge/document_loader.py` (`CURATED_DOCUMENTS`)
- Test: `backend/app/tests/test_knowledge/test_document_loader.py` (criar se não existir)

**Interfaces:**
- Consumes: `KnowledgeDoc(title, category, content, source)`.
- Produces: 2 novos itens em `CURATED_DOCUMENTS` com `source` apontando para os artigos.

- [ ] **Step 1: Write the failing test**

```python
def test_curated_documents_include_article_findings():
    from app.services.knowledge.document_loader import CURATED_DOCUMENTS

    sources = {d.source for d in CURATED_DOCUMENTS}
    assert "https://www.mdpi.com/2076-3417/11/1/313" in sources
    assert "https://pmc.ncbi.nlm.nih.gov/articles/PMC11908068/" in sources

    trust = next(d for d in CURATED_DOCUMENTS
                 if d.source == "https://pmc.ncbi.nlm.nih.gov/articles/PMC11908068/")
    assert "explica" in trust.content.lower() or "transpar" in trust.content.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_knowledge/test_document_loader.py -v"`
Expected: FAIL (sources dos artigos ausentes).

- [ ] **Step 3: Adicionar os documentos curados**

Acrescentar ao final de `CURATED_DOCUMENTS`:

```python
    KnowledgeDoc(
        "Planejamento de treino individualizado por IA (estudo de caso)",
        "ai_methodology_research",
        "Estudo de caso de planejamento de treino individualizado por IA para "
        "ciclistas de estrada modela a carga a partir do histórico do atleta (TSS, "
        "CTL/ATL, distribuição por zona) e ajusta a prescrição ao indivíduo em vez de "
        "um modelo único. Aproveitável para a Training Intelligence Layer: features "
        "derivadas do próprio histórico, validação contra resposta observada e "
        "personalização progressiva conforme mais dados chegam. É apoio à decisão "
        "baseado em dados, não substitui avaliação profissional.",
        source="https://www.mdpi.com/2076-3417/11/1/313",
    ),
    KnowledgeDoc(
        "Confiança e aceitação de planos de treino gerados por IA",
        "ai_trust",
        "A aceitação de planos gerados por IA por atletas recreativos depende de "
        "explicabilidade (mostrar por que cada treino foi sugerido), transparência "
        "sobre os dados e sinais usados, controle do usuário (poder ajustar/recusar), "
        "linguagem clara e não-prescritiva, e validação contra o histórico real. "
        "Recomendações devem expor os sinais (forma, bloco, metodologia) e permitir "
        "manter/ajustar a sugestão. Reforça a transição do treinador humano para a IA "
        "com continuidade respeitosa, sem prometer resultados.",
        source="https://pmc.ncbi.nlm.nih.gov/articles/PMC11908068/",
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: mesmo comando do Step 2.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/knowledge/document_loader.py backend/app/tests/test_knowledge/test_document_loader.py
git commit -m "feat(knowledge): ingere achados dos artigos (MDPI/PMC) como conhecimento curado"
```

---

## Task 5: `workout_adjuster` — transformação determinística pura (2)

**Files:**
- Create: `backend/app/services/planning/workout_adjuster.py`
- Test: `backend/app/tests/test_planning/test_workout_adjuster.py` (criar)

**Interfaces:**
- Consumes: `RiskLevel` (`app.models.enums`); structure dict no formato `StructuredWorkout.model_dump(mode="json")` (`elements: list[Step|Repeat]`, cada `Step` com `intensity`, `duration_s`, `target:{type,low,high}`).
- Produces:
  - `adjust(structure: dict | None, risk_level: RiskLevel) -> AdjustResult`
  - `AdjustResult` = dataclass `{adjusted_structure: dict, change_summary: dict, changed: bool}`
  - helpers puros `to_recovery(structure)`, `cap_intensity(structure, max_zone)`, `scale_volume(structure, factor)` (todos retornam novo dict).

- [ ] **Step 1: Write the failing tests**

```python
from app.models.enums import RiskLevel
from app.services.planning import workout_adjuster as wa

_HARD = {
    "name": "VO2 4x4",
    "elements": [
        {"intensity": "warmup", "duration_s": 600,
         "target": {"type": "power_pct_ftp", "low": 0.55, "high": 0.6}},
        {"count": 4, "steps": [
            {"intensity": "active", "duration_s": 240,
             "target": {"type": "power_pct_ftp", "low": 1.15, "high": 1.2}},  # Z5
            {"intensity": "rest", "duration_s": 180,
             "target": {"type": "power_pct_ftp", "low": 0.5, "high": 0.5}},
        ]},
        {"intensity": "cooldown", "duration_s": 300,
         "target": {"type": "power_pct_ftp", "low": 0.5, "high": 0.5}},
    ],
}


def _max_pct(struct):
    out = []
    for el in struct["elements"]:
        steps = el["steps"] if "steps" in el else [el]
        for s in steps:
            hi = (s["target"] or {}).get("high") or (s["target"] or {}).get("low") or 0
            out.append(hi)
    return max(out)


def test_high_risk_becomes_recovery():
    r = wa.adjust(_HARD, RiskLevel.HIGH)
    assert r.changed is True
    assert _max_pct(r.adjusted_structure) <= 0.75  # sem intensidade
    assert r.change_summary["risk"] == "HIGH"


def test_moderate_caps_intensity_and_trims_volume():
    r = wa.adjust(_HARD, RiskLevel.MODERATE)
    assert r.changed is True
    assert _max_pct(r.adjusted_structure) <= 1.05  # teto Z4
    # volume dos blocos 'active' reduzido
    before = sum(s["duration_s"] for el in _HARD["elements"]
                 for s in (el.get("steps") or [el]) if s["intensity"] == "active")
    after = sum(s["duration_s"] for el in r.adjusted_structure["elements"]
                for s in (el.get("steps") or [el]) if s["intensity"] == "active")
    assert after < before


def test_low_risk_keeps_plan_unchanged():
    r = wa.adjust(_HARD, RiskLevel.LOW)
    assert r.changed is False
    assert r.adjusted_structure == _HARD


def test_adjust_is_idempotent_for_moderate():
    once = wa.adjust(_HARD, RiskLevel.MODERATE).adjusted_structure
    twice = wa.adjust(once, RiskLevel.MODERATE).adjusted_structure
    assert _max_pct(twice) <= 1.05  # capear de novo não estoura o teto


def test_none_structure_is_safe():
    r = wa.adjust(None, RiskLevel.HIGH)
    assert r.changed is False
    assert r.adjusted_structure == {"elements": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_planning/test_workout_adjuster.py -v"`
Expected: FAIL (módulo não existe).

- [ ] **Step 3: Implement `workout_adjuster.py`**

```python
"""Deterministic adjustment of a planned workout to current form/risk.

Pure: operates on the JSON dict of a StructuredWorkout, never touches the DB.
Drives off the guardrail RiskLevel (which already accounts for fatigue,
monotony and ramp). The LLM only writes the human-facing justification.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from app.models.enums import RiskLevel

# %FTP ceiling (fraction) per Coggan zone — upper bound, exclusive-ish.
_ZONE_CEIL = {1: 0.55, 2: 0.75, 3: 0.90, 4: 1.05, 5: 1.20, 6: 1.50, 7: 3.0}

_RECOVERY_CEIL = 0.65   # easy Z1-Z2 spin
_MODERATE_MAX_ZONE = 4
_MODERATE_VOLUME_FACTOR = 0.85


@dataclass
class AdjustResult:
    adjusted_structure: dict
    change_summary: dict = field(default_factory=dict)
    changed: bool = False


def _iter_steps(structure: dict):
    for el in structure.get("elements", []):
        if "steps" in el:
            for s in el["steps"]:
                yield s
        else:
            yield el


def _top_pct(structure: dict) -> float:
    vals = []
    for s in _iter_steps(structure):
        t = s.get("target") or {}
        vals.append(t.get("high") or t.get("low") or 0.0)
    return max(vals, default=0.0)


def _active_seconds(structure: dict) -> int:
    return sum(s.get("duration_s", 0) for s in _iter_steps(structure)
               if s.get("intensity") == "active")


def cap_intensity(structure: dict, max_zone: int) -> dict:
    """Clamp any target above max_zone's ceiling down to that ceiling."""
    ceil = _ZONE_CEIL[max_zone]
    out = copy.deepcopy(structure)
    for s in _iter_steps(out):
        t = s.get("target")
        if not t or t.get("type") != "power_pct_ftp":
            continue
        for k in ("low", "high"):
            if t.get(k) is not None and t[k] > ceil:
                t[k] = ceil
    return out


def scale_volume(structure: dict, factor: float) -> dict:
    """Reduce the duration of 'active' steps by `factor` (min 60s)."""
    out = copy.deepcopy(structure)
    for s in _iter_steps(out):
        if s.get("intensity") == "active":
            s["duration_s"] = max(60, round(s.get("duration_s", 0) * factor))
    return out


def to_recovery(structure: dict) -> dict:
    """Replace the workout with a single easy spin derived from its total time,
    capped at 60 min, at a recovery intensity."""
    total = sum(s.get("duration_s", 0) for s in _iter_steps(structure))
    dur = min(total or 1800, 3600)
    name = structure.get("name") or "Treino"
    return {
        "name": f"{name} (recuperação)",
        "sport": structure.get("sport", "cycling"),
        "elements": [
            {"intensity": "active", "duration_s": dur,
             "target": {"type": "power_pct_ftp", "low": 0.5, "high": _RECOVERY_CEIL}},
        ],
    }


def adjust(structure: dict | None, risk_level: RiskLevel) -> AdjustResult:
    if not structure or not structure.get("elements"):
        return AdjustResult(adjusted_structure={"elements": []}, changed=False,
                            change_summary={"risk": risk_level.value, "note": "sem estrutura"})

    before = {"top_pct": round(_top_pct(structure), 2),
              "active_s": _active_seconds(structure)}

    if risk_level == RiskLevel.HIGH:
        adjusted = to_recovery(structure)
    elif risk_level == RiskLevel.MODERATE:
        adjusted = scale_volume(cap_intensity(structure, _MODERATE_MAX_ZONE),
                                _MODERATE_VOLUME_FACTOR)
    else:  # LOW → mantém
        return AdjustResult(adjusted_structure=structure, changed=False,
                            change_summary={"risk": risk_level.value,
                                            "note": "estado alinhado; manter o planejado",
                                            "before": before, "after": before})

    after = {"top_pct": round(_top_pct(adjusted), 2),
             "active_s": _active_seconds(adjusted)}
    changed = adjusted != structure
    return AdjustResult(adjusted_structure=adjusted, changed=changed,
                        change_summary={"risk": risk_level.value,
                                        "before": before, "after": after})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: mesmo comando do Step 2.
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/planning/workout_adjuster.py backend/app/tests/test_planning/test_workout_adjuster.py
git commit -m "feat(planning): workout_adjuster determinístico (HIGH→recuperação, MODERATE→reduz, LOW→mantém)"
```

---

## Task 6: Coluna `adjustment` + migração + schema (2)

**Files:**
- Modify: `backend/app/models/workout.py` (`WorkoutPlanned` ~115-135)
- Create: `backend/alembic/versions/0008_workout_planned_adjustment.py`
- Modify: `backend/app/schemas/planning.py` (`PlannedWorkoutRead`)
- Test: `backend/app/tests/test_planning/test_workout_adjustment_model.py` (criar)

**Interfaces:**
- Consumes: padrão de migração de `0007` (`PG_UUID`, `revision`/`down_revision`).
- Produces: `WorkoutPlanned.adjustment: dict | None`; `PlannedWorkoutRead.adjustment: dict | None`.

- [ ] **Step 1: Write the failing test (round-trip do campo)**

```python
import pytest
from app.models.workout import WorkoutPlanned
from app.schemas.planning import PlannedWorkoutRead

pytestmark = pytest.mark.asyncio


async def test_planned_workout_carries_adjustment(session):
    from datetime import date
    import uuid
    w = WorkoutPlanned(
        athlete_id=uuid.uuid4(), tenant_id="ta", planned_date=date(2026, 6, 30),
        name="Sweet Spot", structure={"elements": []},
        adjustment={"structure": {"elements": []}, "tss": 40, "reason": "fadiga alta"},
    )
    session.add(w)
    await session.flush()
    await session.refresh(w)
    assert w.adjustment["reason"] == "fadiga alta"

    read = PlannedWorkoutRead.model_validate(w)
    assert read.adjustment["tss"] == 40
```

(Usa a fixture `session` do `conftest`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_planning/test_workout_adjustment_model.py -v"`
Expected: FAIL (`TypeError: 'adjustment' is an invalid keyword` / atributo inexistente).

- [ ] **Step 3: Add the model column**

Em `workout.py`, dentro de `WorkoutPlanned`, após `extra`:

```python
    # AI day-adjustment override (reversível). Original fields stay intact.
    adjustment: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)
```

- [ ] **Step 4: Add the schema field**

Em `planning.py`, em `PlannedWorkoutRead`, após `structure`:

```python
    adjustment: dict | None = None
```

- [ ] **Step 5: Create the Alembic migration**

`backend/alembic/versions/0008_workout_planned_adjustment.py`:

```python
"""Add adjustment jsonb to workouts_planned (AI day-adjustment override).

Revision ID: 0008
Revises: 0007
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workouts_planned", sa.Column("adjustment", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("workouts_planned", "adjustment")
```

> Confirme o tipo jsonb usado nas migrações existentes (ver `0005_workout_extra_jsonb.py`) e espelhe-o (JSONB do dialeto postgres). Se o projeto usa um helper, siga-o.

- [ ] **Step 6: Run test to verify it passes**

Run: mesmo comando do Step 2.
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/workout.py backend/app/schemas/planning.py backend/alembic/versions/0008_workout_planned_adjustment.py backend/app/tests/test_planning/test_workout_adjustment_model.py
git commit -m "feat(planning): coluna adjustment (override reversível) + migração 0008 + schema"
```

---

## Task 7: `generate_day_adjustment` no recommender (2)

**Files:**
- Modify: `backend/app/services/ai/recommender.py`
- Test: `backend/app/tests/test_workout/test_day_adjustment_service.py` (criar)

**Interfaces:**
- Consumes: `workout_adjuster.adjust`; `WorkoutPlanned` (carregado por id); `build_twin`, `evaluate_safety`, `FtpRepository.value_on`, `prompts.render_daily_workout`, `LlmClient`, `RecommendationRepository`; `workout_analysis.{total_duration_s, estimated_tss}`; `StructuredWorkout`.
- Produces:
  - `async def generate_day_adjustment(session, ctx, athlete_id, *, workout_planned: WorkoutPlanned) -> AiRecommendation`
  - Persiste `AiRecommendation(kind="day_adjustment", target_date=workout_planned.planned_date, decision=PENDING)` com `payload = {planned_snapshot, adjusted_structure, change_summary, signals, llm_text}`.

- [ ] **Step 1: Write the failing test**

```python
import uuid
import pytest
from datetime import date, timedelta

from app.core.tenant import TenantContext
from app.models.enums import Role
from app.models.workout import WorkoutPlanned
from app.services.ai.recommender import generate_day_adjustment

pytestmark = pytest.mark.asyncio

_STRUCT = {"name": "Sweet Spot", "sport": "cycling", "elements": [
    {"intensity": "active", "duration_s": 1200,
     "target": {"type": "power_pct_ftp", "low": 0.9, "high": 0.92}}]}


async def test_generate_day_adjustment_persists_recommendation(session):
    aid = uuid.uuid4()
    ctx = TenantContext(athlete_id=aid, tenant_id="ta", role=Role.ATHLETE)
    w = WorkoutPlanned(athlete_id=aid, tenant_id="ta",
                       planned_date=date.today() + timedelta(days=1),
                       name="Sweet Spot", structure=_STRUCT)
    session.add(w)
    await session.flush()

    rec = await generate_day_adjustment(session, ctx, aid, workout_planned=w)
    assert rec.kind == "day_adjustment"
    assert rec.target_date == w.planned_date
    assert "adjusted_structure" in rec.payload
    assert "change_summary" in rec.payload
```

> A camada LLM já degrada com `LlmClient` mock nos testes (ver `recommender` atual rodando em testes). Se `build_twin`/RAG exigirem dados, espelhe o setup mínimo dos testes existentes de recommender (`test_recommender_structured.py`).

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_workout/test_day_adjustment_service.py -v"`
Expected: FAIL (`ImportError: cannot import name 'generate_day_adjustment'`).

- [ ] **Step 3: Implement `generate_day_adjustment`**

Em `recommender.py`, adicionar (reusando os imports já existentes no módulo + `from app.services.planning import workout_adjuster`):

```python
async def generate_day_adjustment(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    *,
    workout_planned,
) -> AiRecommendation:
    """Adjust a single planned workout to current form (deterministic), with an
    LLM-written justification. Seeded by the planned workout, not build_for."""
    ctx.assert_can_access(athlete_id)
    target_date = workout_planned.planned_date

    profile = await profile_context.fetch_profile(session, athlete_id)
    twin = await build_twin(session, ctx, athlete_id, as_of=target_date)
    safety = evaluate_safety(twin.snapshot)

    block = (
        await TrainingWeekRepository(session, ctx).block_on(target_date, athlete_id)
        or BlockType.BASE
    )
    ftp_watts = await FtpRepository(session, ctx).value_on(target_date, athlete_id)

    result = workout_adjuster.adjust(workout_planned.structure, safety.risk_level)
    adjusted_struct = result.adjusted_structure
    adjusted_tss = None
    adjusted_duration_s = None
    if adjusted_struct.get("elements"):
        sw = StructuredWorkout.model_validate(adjusted_struct)
        adjusted_duration_s = workout_analysis.total_duration_s(sw)
        adjusted_tss = workout_analysis.estimated_tss(sw)

    methodology = profile_context.twin_seed_summary(profile)
    evidence_items = await evidence_builder.collect_evidence(
        session, ctx, athlete_id, as_of=target_date
    )
    evidence_text = "\n".join(f"- {e.description}" for e in evidence_items) or "n/d"

    question = (
        f"O treino planejado para {target_date} é '{workout_planned.name}'. "
        f"Estado de forma → risco {safety.risk_level.value}. "
        f"Resumo do ajuste determinístico: {result.change_summary}. "
        "Explique, em PT-BR e sem prometer resultados, por que esse ajuste faz "
        "sentido (ou por que manter o planejado, se não houve mudança), conectando "
        "à forma atual e à metodologia do atleta."
    )
    prompt = prompts.render_daily_workout(
        twin=twin.summary,
        safety=f"risk_level={safety.risk_level.value}",
        evidence=evidence_text,
        knowledge="n/d",
        profile=profile_context.profile_summary(profile),
        methodology=methodology,
        question=question,
    )
    client = LlmClient()
    llm = client.complete(prompt, system=prompts.SYSTEM_PROMPT)
    call_log = LlmCallLog(
        provider=llm.provider, model=llm.model, prompt=prompt, response=llm.text,
        prompt_tokens=llm.prompt_tokens, completion_tokens=llm.completion_tokens,
        latency_ms=llm.latency_ms, estimated_cost_usd=llm.estimated_cost_usd,
        success=llm.success, error_message=llm.error_message,
    )
    session.add(call_log)
    await session.flush()

    template_id = await prompt_store.active_template_id(session, "daily_workout")
    confidence, conf_rationale = _confidence(safety.risk_level, bool(evidence_items))
    rec = AiRecommendation(
        athlete_id=athlete_id, target_date=target_date, kind="day_adjustment",
        question=question, summary=_summary(llm.text, safety),
        physiological_objective=_objective(safety),
        block_relation=f"Ajuste do dia no bloco {block.value} conforme a forma atual.",
        rationale=llm.text if llm.success else "LLM unavailable; ajuste determinístico aplicado.",
        adjust_if_tired="Se mais cansado que o snapshot indica, caia para Z1-Z2 ou descanse.",
        adjust_if_less_time="Com menos tempo, mantenha o bloco principal e corte aquecimento/volume.",
        payload={
            "planned_snapshot": {
                "name": workout_planned.name,
                "structure": workout_planned.structure,
                "planned_tss": workout_planned.planned_tss,
                "planned_duration_s": workout_planned.planned_duration_s,
                "workout_type": getattr(workout_planned.workout_type, "value",
                                        workout_planned.workout_type),
            },
            "adjusted_structure": adjusted_struct,
            "adjusted_tss": adjusted_tss,
            "adjusted_duration_s": adjusted_duration_s,
            "change_summary": result.change_summary,
            "changed": result.changed,
            "signals": _signals(twin.snapshot, methodology, block, ftp_watts),
            "llm_text": llm.text,
        },
        risk_level=safety.risk_level, risk_flags=safety.as_dict(),
        confidence=confidence, confidence_rationale=conf_rationale,
        prompt_template_id=template_id, llm_call_id=call_log.id,
        decision=RecommendationDecision.PENDING,
    )
    await RecommendationRepository(session, ctx).add(rec)
    for ev in evidence_builder.to_models(athlete_id, rec.id, evidence_items):
        session.add(ev)
    await session.flush()
    return rec
```

Adicionar no topo do módulo: `from app.services.planning import workout_adjuster`.

- [ ] **Step 4: Run test to verify it passes**

Run: mesmo comando do Step 2.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/recommender.py backend/app/tests/test_workout/test_day_adjustment_service.py
git commit -m "feat(ai): generate_day_adjustment — ajuste do dia semeado pelo treino planejado"
```

---

## Task 8: Rotas adjust / apply-adjustment / revert (2)

**Files:**
- Modify: `backend/app/api/routes/plans.py`
- Test: `backend/app/tests/test_api/test_day_adjustment.py` (criar)

**Interfaces:**
- Consumes: `generate_day_adjustment` (Task 7); `WorkoutPlanned`; `RecommendationRepository`, `DecisionRepository`, `AiDecision`, `RecommendationDecision`.
- Produces:
  - `POST /plans/workouts/{id}/adjust` → `RecommendationRead` (preview; 201)
  - `POST /plans/workouts/{id}/apply-adjustment` (body `{recommendation_id: uuid}`) → `PlannedWorkoutRead`
  - `DELETE /plans/workouts/{id}/adjustment` → `PlannedWorkoutRead`
  - dia passado em `/adjust` → 409.

- [ ] **Step 1: Write the failing tests**

```python
# imports/fixture client iguais a test_sample_workout.py (sqlite in-memory + token)
from datetime import date, timedelta

async def _make_planned(client, h, when):
    # cria plano+treino via expand seria pesado; em vez disso insere direto pelo banco de teste
    ...  # ver nota abaixo

async def test_adjust_rejects_past_day(client):
    h = {"Authorization": f"Bearer {await _token(client)}"}
    wid = await _seed_planned(client, when=date.today() - timedelta(days=2))
    r = await client.post(f"/api/v1/plans/workouts/{wid}/adjust", headers=h)
    assert r.status_code == 409


async def test_adjust_then_apply_then_revert(client):
    h = {"Authorization": f"Bearer {await _token(client)}"}
    wid = await _seed_planned(client, when=date.today() + timedelta(days=1))

    adj = await client.post(f"/api/v1/plans/workouts/{wid}/adjust", headers=h)
    assert adj.status_code == 201, adj.text
    rec_id = adj.json()["id"]

    apply = await client.post(f"/api/v1/plans/workouts/{wid}/apply-adjustment",
                              headers=h, json={"recommendation_id": rec_id})
    assert apply.status_code == 200
    assert apply.json()["adjustment"] is not None

    rev = await client.delete(f"/api/v1/plans/workouts/{wid}/adjustment", headers=h)
    assert rev.status_code == 200
    assert rev.json()["adjustment"] is None
```

> `_seed_planned` insere um `WorkoutPlanned` (com `structure` válido) diretamente na sessão de teste do override `get_db` — espelhe como outros testes de rota inserem linhas (ou exponha um helper). Ajuste o caminho-base (`/api/v1`) ao prefixo real do app.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_day_adjustment.py -v"`
Expected: FAIL (rotas inexistentes → 404/405).

- [ ] **Step 3: Implement the routes**

Em `plans.py`, adicionar schema de body e as 3 rotas (usar `date.today()` de `datetime`):

```python
from datetime import date

from pydantic import BaseModel

from app.models.ai import AiDecision
from app.models.enums import RecommendationDecision
from app.repositories.ai_repo import DecisionRepository, RecommendationRepository
from app.schemas.ai import RecommendationRead
from app.services.ai.recommender import generate_day_adjustment


class _ApplyAdjustmentBody(BaseModel):
    recommendation_id: uuid.UUID


async def _load_planned_row(db, ctx, workout_planned_id) -> WorkoutPlanned:
    row = (await db.execute(
        select(WorkoutPlanned).where(
            WorkoutPlanned.id == workout_planned_id,
            WorkoutPlanned.athlete_id == ctx.athlete_id,
            WorkoutPlanned.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Treino planejado não encontrado")
    return row


@router.post("/workouts/{workout_planned_id}/adjust",
             response_model=RecommendationRead, status_code=201)
async def adjust_planned_workout(
    workout_planned_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate (preview) an AI day-adjustment for a planned workout. Today or
    future only; does not persist the override."""
    row = await _load_planned_row(db, ctx, workout_planned_id)
    if row.planned_date < date.today():
        raise HTTPException(status_code=409, detail="Não é possível ajustar um dia passado.")
    rec = await generate_day_adjustment(db, ctx, ctx.athlete_id, workout_planned=row)
    await db.refresh(rec, attribute_names=["evidence"])
    return RecommendationRead.model_validate(rec)


@router.post("/workouts/{workout_planned_id}/apply-adjustment",
             response_model=PlannedWorkoutRead)
async def apply_adjustment(
    workout_planned_id: uuid.UUID,
    body: _ApplyAdjustmentBody,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Persist the override from a day-adjustment recommendation onto the day."""
    row = await _load_planned_row(db, ctx, workout_planned_id)
    rec = await RecommendationRepository(db, ctx).get(body.recommendation_id)
    if not rec or rec.kind != "day_adjustment":
        raise HTTPException(status_code=404, detail="Recomendação de ajuste não encontrada")
    p = rec.payload or {}
    from datetime import datetime, timezone
    row.adjustment = {
        "structure": p.get("adjusted_structure"),
        "tss": p.get("adjusted_tss"),
        "duration_s": p.get("adjusted_duration_s"),
        "reason": rec.rationale,
        "recommendation_id": str(rec.id),
        "adjusted_at": datetime.now(timezone.utc).isoformat(),
    }
    db.add(row)
    rec.decision = RecommendationDecision.ACCEPTED
    db.add(rec)
    await DecisionRepository(db, ctx).add(AiDecision(
        athlete_id=ctx.athlete_id, recommendation_id=rec.id,
        decision=RecommendationDecision.ACCEPTED,
    ))
    await db.flush()
    await db.refresh(row)
    return PlannedWorkoutRead.model_validate(row)


@router.delete("/workouts/{workout_planned_id}/adjustment",
               response_model=PlannedWorkoutRead)
async def revert_adjustment(
    workout_planned_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Revert the AI override; the original planned workout is restored."""
    row = await _load_planned_row(db, ctx, workout_planned_id)
    row.adjustment = None
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return PlannedWorkoutRead.model_validate(row)
```

> Também expor `adjustment` no `GET /plans/{plan_id}/workouts` já acontece via `PlannedWorkoutRead` (Task 6). O helper `_planned_workout` existente (export) permanece.

- [ ] **Step 4: Run tests to verify they pass**

Run: mesmo comando do Step 2.
Expected: PASS (rejeita passado; adjust→apply→revert).

- [ ] **Step 5: Add a multi-tenant isolation test**

```python
async def test_apply_adjustment_isolated_per_tenant(client):
    # athlete B não consegue aplicar ajuste num workout de A (404 no load).
    ...  # cria workout do tenant A; usa token de B; espera 404
```

Rodar e garantir verde.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/plans.py backend/app/tests/test_api/test_day_adjustment.py
git commit -m "feat(api): rotas de ajuste do dia (adjust/apply/revert) com isolamento e bloqueio de passado"
```

---

## Task 9: Calendário mostra valores efetivos + selo "IA" (2)

**Files:**
- Modify: `frontend/calendar_view.py`
- Test: `frontend/test_calendar_view.py`

**Interfaces:**
- Consumes: dict de treino planejado com chave opcional `adjustment: {structure, tss, duration_s, ...} | None`.
- Produces:
  - `effective_workout(w: dict) -> tuple[dict, bool]` — retorna (treino efetivo, `is_adjusted`). Quando há `adjustment`, sobrepõe `structure`/`planned_tss`/`planned_duration_s`.
  - `_day_cell_html` renderiza selo "🤖 IA" quando `is_adjusted`.

- [ ] **Step 1: Write the failing test**

Em `test_calendar_view.py`:

```python
def test_effective_workout_prefers_adjustment():
    from calendar_view import effective_workout
    w = {"name": "Sweet Spot", "planned_tss": 80, "planned_duration_s": 3600,
         "structure": {"elements": [{"intensity": "active", "duration_s": 3600,
                                     "target": {"type": "power_pct_ftp", "low": 0.9}}]},
         "adjustment": {"structure": {"elements": []}, "tss": 30, "duration_s": 1800}}
    eff, is_adj = effective_workout(w)
    assert is_adj is True
    assert eff["planned_tss"] == 30
    assert eff["planned_duration_s"] == 1800
    assert eff["structure"] == {"elements": []}


def test_effective_workout_without_adjustment():
    from calendar_view import effective_workout
    w = {"name": "X", "planned_tss": 80, "structure": {"elements": []}}
    eff, is_adj = effective_workout(w)
    assert is_adj is False
    assert eff is w


def test_day_cell_shows_ai_badge_when_adjusted():
    from datetime import date
    from calendar_view import _day_cell_html
    w = {"name": "Sweet Spot", "workout_type": "SWEET_SPOT", "planned_tss": 30,
         "planned_duration_s": 1800, "structure": {"elements": []},
         "adjustment": {"structure": {"elements": []}, "tss": 30, "duration_s": 1800}}
    html = _day_cell_html(date(2026, 6, 30), w, [], date(2026, 6, 30))
    assert "IA" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest test_calendar_view.py -k 'effective or badge' -q"`
Expected: FAIL (`effective_workout` não existe; sem "IA" no html).

- [ ] **Step 3: Implement `effective_workout` + badge**

Em `calendar_view.py`:

```python
def effective_workout(w: dict) -> tuple[dict, bool]:
    """Return (effective workout, is_adjusted). When an AI override exists, its
    structure/tss/duration take precedence; the original dict is left intact."""
    adj = w.get("adjustment")
    if not adj:
        return w, False
    eff = dict(w)
    if adj.get("structure") is not None:
        eff["structure"] = adj["structure"]
    if adj.get("tss") is not None:
        eff["planned_tss"] = adj["tss"]
    if adj.get("duration_s") is not None:
        eff["planned_duration_s"] = adj["duration_s"]
    return eff, True
```

Em `_day_cell_html`, no início (após o early-return de descanso), usar o efetivo e montar o selo:

```python
    w, is_adjusted = effective_workout(w)
    ...
    badge = '<span class="ai-badge">🤖 IA</span>' if is_adjusted else ""
```

e inserir `{badge}` na `wk-head` (ao lado do nome). Adicionar ao `_CALENDAR_CSS`:

```css
.ai-badge{font-size:9px;font-weight:800;color:#2f6fed;background:rgba(47,111,237,.12);
  padding:1px 6px;border-radius:20px;margin-left:4px}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: mesmo comando do Step 2.
Expected: PASS.

- [ ] **Step 5: Run the full frontend suite**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest -q"`
Expected: tudo verde (testes existentes do calendário não quebram).

- [ ] **Step 6: Commit**

```bash
git add frontend/calendar_view.py frontend/test_calendar_view.py
git commit -m "feat(frontend): calendário usa valores efetivos do ajuste + selo IA"
```

---

## Task 10: Painel de detalhe — botões Ajustar/Aceitar/Manter/Reverter (2)

**Files:**
- Modify: `frontend/app.py` (`_render_day_detail` ~456-482; `_render_calendar` `by_date` montagem ~384)

**Interfaces:**
- Consumes: rotas `POST /plans/workouts/{id}/adjust`, `POST .../apply-adjustment`, `DELETE .../adjustment`; `calendar_view.effective_workout`.
- Produces: UI de ajuste do dia; o calendário passa a usar valores efetivos.

> UI Streamlit é difícil de testar unitariamente; este task é validado manualmente (Step 4). Mantém a lógica testável já coberta na Task 9 (`effective_workout`).

- [ ] **Step 1: Usar valores efetivos ao montar o calendário**

Em `_render_calendar`, ao montar `by_date`, manter o dict original (o `calendar_view` já aplica `effective_workout` internamente no `_day_cell_html`). Nenhuma mudança necessária se `_day_cell_html` chama `effective_workout` (Task 9). **Verifique**: o cálculo do TSS planejado da semana em `calendar_html` usa `by_date[...]["planned_tss"]` — para refletir o ajuste no total semanal, aplicar `effective_workout` também em `calendar_html` ao somar. Editar `calendar_html`:

```python
    plan_tss = 0.0
    for d in week:
        wd = by_date.get(d.isoformat())
        if wd:
            eff, _ = effective_workout(wd)
            plan_tss += (eff.get("planned_tss") or 0)
```

(Substitui a list-comprehension atual de `plan_tss`.)

- [ ] **Step 2: Adicionar a seção de ajuste no painel de detalhe**

Em `_render_day_detail(token, w, acts, iso)`, após o bloco de download, adicionar (apenas para hoje/futuro):

```python
    from datetime import date as _date
    d = _date.fromisoformat(iso)
    if d >= _date.today():
        st.divider()
        st.markdown("#### 🤖 Ajustar este treino com a IA")
        adj = w.get("adjustment")
        if adj:
            st.info(f"Treino ajustado pela IA · {round(adj.get('tss') or 0)} TSS. "
                    f"Motivo: {adj.get('reason') or '—'}")
            if st.button("↩️ Reverter para o planejado", key=f"revert_{w['id']}"):
                r = api("DELETE", f"/plans/workouts/{w['id']}/adjustment", token=token)
                st.rerun() if r.status_code == 200 else st.error(r.text)
        else:
            if st.button("Ajustar ao meu estado de hoje", key=f"adjust_{w['id']}"):
                r = api("POST", f"/plans/workouts/{w['id']}/adjust", token=token)
                if r.status_code == 201:
                    st.session_state[f"adjpreview_{w['id']}"] = r.json()
                else:
                    st.error(r.text)
            preview = st.session_state.get(f"adjpreview_{w['id']}")
            if preview:
                pl = preview.get("payload") or {}
                risk = preview["risk_level"]
                color = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🔴"}.get(risk, "⚪")
                st.markdown(f"**{color} Risco: {risk}** · {preview.get('summary')}")
                if pl.get("changed"):
                    st.caption(f"Ajustado: {round(pl.get('adjusted_tss') or 0)} TSS "
                               f"(planejado {round((pl.get('planned_snapshot') or {}).get('planned_tss') or 0)} TSS)")
                    detail = cv.detail_html(pl.get("adjusted_structure"))
                    if detail:
                        components.html(detail, height=cv.detail_height(), scrolling=False)
                else:
                    st.success("Seu estado está alinhado ao planejado — mantenha o treino.")
                st.write(preview.get("rationale"))
                c1, c2 = st.columns(2)
                if pl.get("changed") and c1.button("✅ Aceitar ajuste", key=f"acc_{w['id']}"):
                    a = api("POST", f"/plans/workouts/{w['id']}/apply-adjustment",
                            token=token, json={"recommendation_id": preview["id"]})
                    if a.status_code == 200:
                        st.session_state.pop(f"adjpreview_{w['id']}", None)
                        st.rerun()
                    else:
                        st.error(a.text)
                if c2.button("Manter planejado", key=f"keep_{w['id']}"):
                    st.session_state.pop(f"adjpreview_{w['id']}", None)
                    st.rerun()
```

(`cv` e `components` já estão importados em `app.py`.)

- [ ] **Step 3: Verificar imports/símbolos**

Confirme que `_render_day_detail` recebe `w` com a chave `id` (vem de `by_date[sel]`, que é a linha de `/plans/{id}/workouts` → tem `id`). Confirme que `effective_workout` está importado/disponível em `calendar_view` (Task 9).

- [ ] **Step 4: Validação manual (sobe o stack)**

```bash
docker compose up -d --build api frontend
```

Login dev (`leandro@athletehub.example.com` / `leandro12345`), aba 📅 Plano → selecionar **hoje** (ou um dia futuro) → "Ajustar ao meu estado de hoje" → ver planejado × ajustado + motivo → "Aceitar ajuste" → confirmar selo "🤖 IA" na célula e total semanal atualizado → "Reverter" volta ao planejado. Repetir num dia passado: o bloco de ajuste não aparece. Registrar evidência (screenshot/observação).

- [ ] **Step 5: Commit**

```bash
git add frontend/app.py frontend/calendar_view.py
git commit -m "feat(frontend): painel de ajuste do dia (ajustar/aceitar/manter/reverter) + total semanal efetivo"
```

---

## Task 11: Repovoar o twin_seed do Leandro + verificação ponta a ponta

**Files:** nenhum (operacional).

- [ ] **Step 1: Repovoar o perfil com as novas chaves de metodologia**

```bash
docker exec aath_api python -m app.scripts.analyze_athlete --email leandro@athletehub.example.com
```

Confirmar no log/saída que rodou sem erro. (Também ocorre auto no próximo `/imports/upload` produtivo.)

- [ ] **Step 2: Conferir que a base de conhecimento está populada**

Após o `docker compose up` (Task 10), verificar nos logs `knowledge_seeded` (ou `make seed-knowledge` como fallback). Gerar uma recomendação normal e confirmar no painel "🔍 Baseado em" que a metodologia agora reflete taper/terminologia/periodização.

- [ ] **Step 3: Rodar as suítes completas**

Backend (alvo dos diretórios tocados) e frontend:
```bash
docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_analysis app/tests/test_ai app/tests/test_planning app/tests/test_knowledge app/tests/test_api -q"
docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest -q"
```
Expected: verde. Atualizar `.superpowers/sdd/progress.md` com o estado final.

- [ ] **Step 4: Commit (se houver mudança de progresso/docs)**

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs: progresso — inteligência com contexto completo + ajuste do dia concluído"
```

---

## Self-Review (preenchido pelo autor do plano)

**Cobertura do spec:**
- 1a (twin_seed + injeção) → Tasks 1, 2 ✓
- 1b (auto-seed startup) → Task 3 ✓
- 1c (artigos curados) → Task 4 ✓
- 2 (adjuster) → Task 5 ✓; (coluna+migração+schema) → Task 6 ✓; (generate_day_adjustment) → Task 7 ✓; (rotas) → Task 8 ✓; (calendário/selo) → Task 9 ✓; (UI painel) → Task 10 ✓; (repovoamento+verificação) → Task 11 ✓
- Não-objetivos respeitados (sem replanejar semana, sem LLM gerando treino, sem Celery).

**Consistência de tipos:** `adjust(structure, risk_level) -> AdjustResult{adjusted_structure, change_summary, changed}` usado igual nas Tasks 5/7. `effective_workout(w)->(dict,bool)` igual nas Tasks 9/10. `generate_day_adjustment(..., workout_planned)` igual nas Tasks 7/8. Payload keys (`adjusted_structure`, `adjusted_tss`, `change_summary`, `changed`, `planned_snapshot`) consistentes entre Tasks 7/8/10. Coluna `adjustment` (Task 6) consumida nas Tasks 8/9/10.

**Riscos sinalizados ao executor:** (a) inserts de `embeddings` exigem pgvector — testes de conhecimento isolam por documento; (b) montar `WorkoutPlanned` nos testes de rota requer inserir direto na sessão de teste; (c) confirmar prefixo de rota real (`/api/v1`) e diretórios de teste existentes antes de criar arquivos.
