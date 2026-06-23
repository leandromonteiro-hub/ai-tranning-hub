# Personalization (Anamnese + Check-in) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coletar a anamnese (obrigatória) e o check-in diário na UI, injetar o perfil do atleta no prompt da IA, e bloquear recomendações até a anamnese estar completa — tornando as recomendações personalizadas.

**Architecture:** Backend — enriquecer `AthleteProfile` (+migração), módulo `profile_context` (fetch/completo/resumo), gate 409 em `POST /recommendations`, e injetar o resumo do perfil no template versionado (v2). Frontend — abas "🩺 Anamnese" (gate de onboarding) e "📝 Check-in diário", com a aba Recomendações bloqueada enquanto a anamnese estiver incompleta.

**Tech Stack:** FastAPI/SQLAlchemy/Pydantic/Alembic (backend), pytest, Streamlit+httpx (frontend, sem testes de UI → `ast.parse` + verificação ao vivo).

## Global Constraints

- **Campos obrigatórios da anamnese (fonte única, back e front idênticos):** `birth_date, sex, weight_kg, height_cm, max_hr, primary_discipline, years_training, goals, weekly_hours`. "Completo" = todos esses não-nulos e não-vazios.
- **Campos novos do perfil (todos nullable / default):** `goals` (Text), `weekly_hours` (Float), `weekly_days` (Integer), `injury_history` (Text), `medical_conditions` (Text), `has_power_meter` (Boolean default False), `has_hr_monitor` (Boolean default False).
- **Gate:** `POST /recommendations` → **409** `detail="Anamnese incompleta — complete seu perfil antes de gerar recomendações."` quando incompleta.
- **Prompt:** novo slot `{profile}` no `DAILY_WORKOUT_TEMPLATE`; `ACTIVE_TEMPLATES["daily_workout"]` sobe para versão **2**.
- Tenant-scoped: tudo do atleta logado (`ctx.athlete_id`).
- **Comando teste backend (raiz do repo):** `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <caminho> -v"`
- **Comando sintaxe frontend (raiz do repo):** `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); print('syntax OK')"`
- Ordem final das abas: `🩺 Anamnese, 📈 Forma & Carga, 📥 Importar, 📝 Check-in, 🏁 Provas, 📅 Plano, 🧠 Recomendações`.
- Commits frequentes, um por task.

---

### Task 1: Enriquecer `AthleteProfile` (modelo + schema + migração 0004)

**Files:**
- Modify: `backend/app/models/athlete.py` (classe `AthleteProfile`)
- Modify: `backend/app/schemas/athlete.py` (classe `AthleteProfileBase`)
- Create: `backend/app/alembic/versions/0004_athlete_profile_anamnese.py` → na verdade `backend/alembic/versions/0004_athlete_profile_anamnese.py`
- Test: `backend/app/tests/test_api/test_anamnese.py` (novo)

**Interfaces:**
- Produces: `AthleteProfile` e `AthleteProfileRead`/`Update` passam a ter os 7 campos novos; `GET/PUT /athletes/me/profile` aceitam/retornam eles.

- [ ] **Step 1: Escrever o teste que falha** — `backend/app/tests/test_api/test_anamnese.py`:

```python
"""Anamnese: the athlete profile accepts and returns the enriched fields."""
from __future__ import annotations

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

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        s.add(Athlete(email="a@example.com", hashed_password=hash_password("pw12345678"),
                      full_name="A", role=Role.ATHLETE, tenant_id="ta"))
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


async def _token(client):
    r = await client.post("/api/v1/auth/login", data={"username": "a@example.com", "password": "pw12345678"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def test_profile_accepts_enriched_anamnese_fields(client):
    h = {"Authorization": f"Bearer {await _token(client)}"}
    body = {
        "birth_date": "1990-05-10", "sex": "M", "weight_kg": 72.0, "height_cm": 178.0,
        "max_hr": 188, "resting_hr": 52, "primary_discipline": "XCO", "years_training": 6,
        "goals": "Vencer a maratona regional", "weekly_hours": 8.0, "weekly_days": 4,
        "injury_history": "tendinite no joelho em 2024", "medical_conditions": "nenhuma",
        "has_power_meter": True, "has_hr_monitor": True,
    }
    put = await client.put("/api/v1/athletes/me/profile", headers=h, json=body)
    assert put.status_code == 200, put.text
    got = await client.get("/api/v1/athletes/me/profile", headers=h)
    assert got.status_code == 200, got.text
    p = got.json()
    assert p["goals"] == "Vencer a maratona regional"
    assert p["weekly_hours"] == 8.0 and p["weekly_days"] == 4
    assert p["injury_history"] == "tendinite no joelho em 2024"
    assert p["has_power_meter"] is True and p["has_hr_monitor"] is True
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_anamnese.py -v"`
Expected: FAIL (PUT ignora/`422` ou GET sem as chaves novas — os campos não existem ainda).

- [ ] **Step 3: Adicionar os campos no modelo** — em `backend/app/models/athlete.py`, na classe `AthleteProfile`, logo após a linha `notes: Mapped[str | None] = mapped_column(Text, nullable=True)`:

```python
    goals: Mapped[str | None] = mapped_column(Text, nullable=True)
    weekly_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    weekly_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    injury_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    medical_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_power_meter: Mapped[bool] = mapped_column(Boolean, default=False)
    has_hr_monitor: Mapped[bool] = mapped_column(Boolean, default=False)
```

(`Boolean`, `Float`, `Integer`, `Text` já estão importados em `athlete.py`.)

- [ ] **Step 4: Adicionar os campos no schema** — em `backend/app/schemas/athlete.py`, na classe `AthleteProfileBase`, após `notes: str | None = None`:

```python
    goals: str | None = None
    weekly_hours: float | None = None
    weekly_days: int | None = None
    injury_history: str | None = None
    medical_conditions: str | None = None
    has_power_meter: bool = False
    has_hr_monitor: bool = False
```

- [ ] **Step 5: Criar a migração** — `backend/alembic/versions/0004_athlete_profile_anamnese.py`:

```python
"""Enrich athlete_profiles with anamnese fields.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TEXT_COLS = ("goals", "injury_history", "medical_conditions")
_OTHER = (
    ("weekly_hours", sa.Float()),
    ("weekly_days", sa.Integer()),
)
_BOOL_COLS = ("has_power_meter", "has_hr_monitor")


def upgrade() -> None:
    for c in _TEXT_COLS:
        op.add_column("athlete_profiles", sa.Column(c, sa.Text(), nullable=True))
    for name, type_ in _OTHER:
        op.add_column("athlete_profiles", sa.Column(name, type_, nullable=True))
    for c in _BOOL_COLS:
        op.add_column("athlete_profiles", sa.Column(c, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    for c in (*_BOOL_COLS, "weekly_days", "weekly_hours", *_TEXT_COLS):
        op.drop_column("athlete_profiles", c)
```

- [ ] **Step 6: Rodar o teste (e a suíte)**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_anamnese.py -v && python -m pytest -q"`
Expected: o teste novo passa; suíte total verde (73 + 1).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/athlete.py backend/app/schemas/athlete.py backend/alembic/versions/0004_athlete_profile_anamnese.py backend/app/tests/test_api/test_anamnese.py
git commit -m "feat(profile): enrich AthleteProfile with anamnese fields (+migration)"
```

---

### Task 2: Gate de anamnese + injeção do perfil no prompt

**Files:**
- Create: `backend/app/services/ai/profile_context.py`
- Modify: `backend/app/services/ai/prompts.py` (template + render + versão)
- Modify: `backend/app/services/ai/recommender.py` (buscar perfil + passar ao render)
- Modify: `backend/app/api/routes/recommendations.py` (`create_recommendation` → gate)
- Test: `backend/app/tests/test_ai/test_profile_context.py` (novo), `backend/app/tests/test_api/test_recommendation_gate.py` (novo)

**Interfaces:**
- Consumes: `AthleteProfile` (campos da Task 1); `generate_recommendation`; `render_daily_workout`.
- Produces: `profile_context.fetch_profile(session, athlete_id)`, `profile_context.anamnese_complete(profile)`, `profile_context.profile_summary(profile)`; `render_daily_workout(..., profile=...)`; `POST /recommendations` retorna 409 sem anamnese.

- [ ] **Step 1: Escrever os testes que falham**

`backend/app/tests/test_ai/__init__.py` (vazio) e `backend/app/tests/test_ai/test_profile_context.py`:

```python
from datetime import date

from app.models.athlete import AthleteProfile
from app.services.ai.profile_context import anamnese_complete, profile_summary


def _full() -> AthleteProfile:
    return AthleteProfile(
        birth_date=date(1990, 5, 10), sex="M", weight_kg=72.0, height_cm=178.0,
        max_hr=188, resting_hr=52, primary_discipline="XCO", years_training=6,
        goals="Vencer a maratona", weekly_hours=8.0, weekly_days=4,
    )


def test_anamnese_complete_true_when_all_required_present():
    assert anamnese_complete(_full()) is True


def test_anamnese_incomplete_when_missing_required():
    p = _full()
    p.goals = None
    assert anamnese_complete(p) is False
    assert anamnese_complete(None) is False


def test_profile_summary_includes_key_fields():
    s = profile_summary(_full())
    assert "Vencer a maratona" in s
    assert "XCO" in s
    assert "72" in s and "188" in s


def test_profile_summary_none_is_nd():
    assert profile_summary(None) == "n/d"
```

`backend/app/tests/test_api/test_recommendation_gate.py`:

```python
"""POST /recommendations is gated on a complete anamnese (HTTP 409)."""
from __future__ import annotations

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

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        s.add(Athlete(email="a@example.com", hashed_password=hash_password("pw12345678"),
                      full_name="A", role=Role.ATHLETE, tenant_id="ta"))
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


async def _token(client):
    r = await client.post("/api/v1/auth/login", data={"username": "a@example.com", "password": "pw12345678"})
    return r.json()["access_token"]


async def test_recommendation_blocked_without_anamnese_then_allowed(client):
    h = {"Authorization": f"Bearer {await _token(client)}"}
    blocked = await client.post("/api/v1/recommendations", headers=h, json={"kind": "daily_workout"})
    assert blocked.status_code == 409, blocked.text

    body = {
        "birth_date": "1990-05-10", "sex": "M", "weight_kg": 72.0, "height_cm": 178.0,
        "max_hr": 188, "primary_discipline": "XCO", "years_training": 6,
        "goals": "Vencer a maratona", "weekly_hours": 8.0,
    }
    assert (await client.put("/api/v1/athletes/me/profile", headers=h, json=body)).status_code == 200
    ok = await client.post("/api/v1/recommendations", headers=h, json={"kind": "daily_workout"})
    assert ok.status_code == 201, ok.text
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_ai/test_profile_context.py app/tests/test_api/test_recommendation_gate.py -v"`
Expected: FAIL (módulo `profile_context` inexistente; sem gate o POST devolve 201 em vez de 409).

- [ ] **Step 3: Criar `profile_context.py`** — `backend/app/services/ai/profile_context.py`:

```python
"""Athlete profile (anamnese) helpers for the recommendation pipeline.

Fetches the athlete's profile, decides whether the anamnese is complete enough
to allow recommendations, and renders a one-line summary injected into the LLM
prompt so recommendations are personalised.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import AthleteProfile

# Single source of truth for "anamnese complete" (mirrored in the frontend).
REQUIRED_FIELDS = (
    "birth_date", "sex", "weight_kg", "height_cm", "max_hr",
    "primary_discipline", "years_training", "goals", "weekly_hours",
)


async def fetch_profile(session: AsyncSession, athlete_id: uuid.UUID) -> AthleteProfile | None:
    res = await session.execute(
        select(AthleteProfile).where(
            AthleteProfile.athlete_id == athlete_id,
            AthleteProfile.deleted_at.is_(None),
        )
    )
    return res.scalar_one_or_none()


def anamnese_complete(profile: AthleteProfile | None) -> bool:
    if profile is None:
        return False
    return all(getattr(profile, f) not in (None, "") for f in REQUIRED_FIELDS)


def profile_summary(profile: AthleteProfile | None) -> str:
    if profile is None:
        return "n/d"
    parts: list[str] = []
    if profile.birth_date:
        parts.append(f"{(date.today() - profile.birth_date).days // 365} anos")
    if profile.sex:
        parts.append(profile.sex)
    if profile.weight_kg:
        parts.append(f"{profile.weight_kg:.0f}kg")
    if profile.height_cm:
        parts.append(f"{profile.height_cm:.0f}cm")
    if profile.max_hr:
        parts.append(f"FCmax {profile.max_hr}")
    if profile.resting_hr:
        parts.append(f"FCrep {profile.resting_hr}")
    if profile.years_training is not None:
        parts.append(f"{profile.years_training} anos de treino")
    if profile.primary_discipline:
        parts.append(profile.primary_discipline)
    line = ", ".join(parts) if parts else "n/d"

    extra: list[str] = []
    if profile.goals:
        extra.append(f"Objetivos: {profile.goals}")
    if profile.weekly_hours is not None:
        days = f", {profile.weekly_days}d" if profile.weekly_days else ""
        extra.append(f"Disponibilidade: {profile.weekly_hours:.0f}h/sem{days}")
    if profile.injury_history:
        extra.append(f"Lesões/limitações: {profile.injury_history}")
    if profile.medical_conditions:
        extra.append(f"Condições médicas: {profile.medical_conditions}")
    equip = [n for n, v in (("potência", profile.has_power_meter), ("FC", profile.has_hr_monitor)) if v]
    if equip:
        extra.append("Equipamento: " + "+".join(equip))
    return line + ((" · " + " · ".join(extra)) if extra else "")
```

- [ ] **Step 4: Adicionar o slot `{profile}` no prompt (versão 2)** — em `backend/app/services/ai/prompts.py`, substituir o `DAILY_WORKOUT_TEMPLATE`, o `render_daily_workout` e o `ACTIVE_TEMPLATES` por:

```python
DAILY_WORKOUT_TEMPLATE = """\
Athlete profile (anamnese — who this athlete is):
{profile}

Athlete digital-twin snapshot:
{twin}

Safety guardrail result (already computed — respect it):
{safety}

Relevant historical evidence (the athlete's own data):
{evidence}

Relevant training-knowledge context:
{knowledge}

Athlete question / request:
{question}

Produce a single recommendation as structured guidance including: the
physiological objective, how it relates to the current block and target race,
the supporting evidence, a confidence level (0-1) with justification, identified
risks, how to scale down if the athlete is more tired, and how to scale down if
they have less time available today. Tailor it to the athlete profile above
(experience, goals, weekly availability, injuries/limitations).
"""


def render_daily_workout(
    twin: str, safety: str, evidence: str, knowledge: str, question: str,
    profile: str = "n/d",
) -> str:
    return DAILY_WORKOUT_TEMPLATE.format(
        profile=profile, twin=twin, safety=safety, evidence=evidence,
        knowledge=knowledge, question=question or "Recommend today's workout.",
    )


def template_hash(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


# Registry of active templates (name -> (version, body)).
ACTIVE_TEMPLATES = {
    "daily_workout": (2, DAILY_WORKOUT_TEMPLATE),
}
```

- [ ] **Step 5: Injetar o perfil no recomendador** — em `backend/app/services/ai/recommender.py`:

(a) nos imports (junto aos outros `from app.services.ai...`), adicionar:
```python
from app.services.ai import profile_context
```

(b) logo após `target_date = target_date or date.today()` (antes de `# 1. Digital twin`), adicionar:
```python
    profile = await profile_context.fetch_profile(session, athlete_id)
```

(c) na chamada `prompts.render_daily_workout(...)`, adicionar o argumento `profile`:
```python
    prompt = prompts.render_daily_workout(
        twin=twin.summary,
        safety=safety_text,
        evidence=evidence_text,
        knowledge=knowledge_text,
        profile=profile_context.profile_summary(profile),
        question=query if not safety.block_original else (
            query + "\n\nNOTE: guardrails flagged HIGH risk — you MUST recommend a "
            "conservative recovery-oriented alternative only."
        ),
    )
```

- [ ] **Step 6: Gate no endpoint** — em `backend/app/api/routes/recommendations.py`:

(a) nos imports, adicionar:
```python
from app.services.ai.profile_context import anamnese_complete, fetch_profile
```

(b) no início de `create_recommendation`, antes de chamar `generate_recommendation`:
```python
    profile = await fetch_profile(db, ctx.athlete_id)
    if not anamnese_complete(profile):
        raise HTTPException(
            status_code=409,
            detail="Anamnese incompleta — complete seu perfil antes de gerar recomendações.",
        )
```

- [ ] **Step 7: Atualizar os testes existentes que pedem recomendação sem anamnese**

O novo gate faz `POST /recommendations` retornar 409 quando não há anamnese completa. Três testes existentes criam uma recomendação via esse endpoint **sem** anamnese e passariam a falhar. Em cada um, **antes da primeira chamada** `POST /api/v1/recommendations`, inserir um PUT de anamnese completa usando o mesmo header de auth do atleta que faz a chamada (mesmo `maker`/cliente do teste):

```python
    # anamnese completa é pré-requisito para gerar recomendações
    await client.put("/api/v1/athletes/me/profile", headers=<HEADER_DO_ATLETA>, json={
        "birth_date": "1990-05-10", "sex": "M", "weight_kg": 72.0, "height_cm": 178.0,
        "max_hr": 188, "primary_discipline": "XCO", "years_training": 6,
        "goals": "Validação", "weekly_hours": 8.0,
    })
```

Aplicar em (ler cada arquivo para achar o ponto exato e o nome do cliente/header):
- `backend/app/tests/test_api/test_app.py` → `test_recommendation_and_feedback_flow` (atleta `a@example.com`, header `h`, cliente `client`).
- `backend/app/tests/test_api/test_workout_export.py` → o teste que faz `POST /recommendations` para o atleta A (header `ha`, cliente `client_with_ftp`).
- `backend/app/tests/test_api/test_admin_panel.py` → `test_admin_feedback_includes_athlete_id` (atleta `a@example.com`, header `ath`, cliente `client_admin`) — inserir o PUT antes do `POST /recommendations`.

Não alterar a regra do gate. Se algum desses testes usar um athlete sem rota de profile acessível, ajustar para logar como esse atleta e fazer o PUT com o header dele.

- [ ] **Step 8: Rodar os testes + suíte completa**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest -q"`
Expected: suíte total verde (novos testes + os 3 atualizados + os demais). Se algum teste fora desses três quebrar pelo gate, atualizá-lo do mesmo modo (PUT de anamnese antes do POST). Reportar o total no relatório.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/ai/profile_context.py backend/app/services/ai/prompts.py backend/app/services/ai/recommender.py backend/app/api/routes/recommendations.py backend/app/tests/
git commit -m "feat(ai): gate recommendations on anamnese + inject athlete profile into prompt"
```

---

### Task 3: Frontend — aba "🩺 Anamnese" + gate de onboarding

**Files:**
- Modify: `frontend/app.py`

**Interfaces:**
- Consumes: `api(...)`, `date` (importado na fatia anterior), `dashboard`, `recommendations_tab`.
- Produces: `anamnese_tab(token)`, helper `_anamnese_complete(profile)`; `dashboard` mostra o gate e passa `anamnese_ok` para `recommendations_tab`.

- [ ] **Step 1: Adicionar o helper + a aba** — inserir imediatamente antes de `def dashboard(token: str) -> None:` em `frontend/app.py`:

```python
_ANAMNESE_REQUIRED = (
    "birth_date", "sex", "weight_kg", "height_cm", "max_hr",
    "primary_discipline", "years_training", "goals", "weekly_hours",
)


def _anamnese_complete(profile: dict | None) -> bool:
    if not profile:
        return False
    return all(profile.get(f) not in (None, "") for f in _ANAMNESE_REQUIRED)


def anamnese_tab(token: str) -> None:
    st.subheader("🩺 Anamnese")
    st.caption("Preencha seu perfil — obrigatório para gerar recomendações personalizadas.")
    p = api("GET", "/athletes/me/profile", token=token)
    cur = (p.json() or {}) if p.status_code == 200 else {}
    sexes = ["M", "F", "Outro"]
    with st.form("anamnese"):
        birth = st.date_input(
            "Data de nascimento",
            value=date.fromisoformat(cur["birth_date"]) if cur.get("birth_date") else date(1990, 1, 1),
        )
        sex = st.selectbox("Sexo", sexes, index=sexes.index(cur["sex"]) if cur.get("sex") in sexes else 0)
        weight = st.number_input("Peso (kg)", 30.0, 200.0, float(cur.get("weight_kg") or 70.0), step=0.5)
        height = st.number_input("Altura (cm)", 120.0, 230.0, float(cur.get("height_cm") or 175.0), step=1.0)
        max_hr = st.number_input("FC máxima", 120, 230, int(cur.get("max_hr") or 185))
        resting_hr = st.number_input("FC repouso", 30, 120, int(cur.get("resting_hr") or 55))
        discipline = st.text_input("Disciplina principal (ex.: XCO, Maratona)", cur.get("primary_discipline") or "")
        years = st.number_input("Anos de treino", 0, 60, int(cur.get("years_training") or 1))
        goals = st.text_area("Objetivos", cur.get("goals") or "")
        weekly_hours = st.number_input("Disponibilidade (horas/semana)", 0.0, 40.0, float(cur.get("weekly_hours") or 6.0), step=0.5)
        weekly_days = st.number_input("Dias disponíveis/semana", 0, 7, int(cur.get("weekly_days") or 4))
        injury = st.text_area("Histórico de lesões/limitações", cur.get("injury_history") or "")
        medical = st.text_area("Condições médicas/medicações", cur.get("medical_conditions") or "")
        power = st.checkbox("Tenho medidor de potência", value=bool(cur.get("has_power_meter")))
        hrmon = st.checkbox("Tenho monitor de FC", value=bool(cur.get("has_hr_monitor")))
        if st.form_submit_button("Salvar anamnese"):
            body = {
                "birth_date": birth.isoformat(), "sex": sex, "weight_kg": weight, "height_cm": height,
                "max_hr": int(max_hr), "resting_hr": int(resting_hr),
                "primary_discipline": discipline or None, "years_training": int(years),
                "goals": goals or None, "weekly_hours": weekly_hours, "weekly_days": int(weekly_days),
                "injury_history": injury or None, "medical_conditions": medical or None,
                "has_power_meter": power, "has_hr_monitor": hrmon,
            }
            r = api("PUT", "/athletes/me/profile", token=token, json=body)
            if r.status_code == 200:
                st.success("Anamnese salva.")
                st.rerun()
            else:
                st.error(r.text)
```

- [ ] **Step 2: Gate no dashboard + passar `anamnese_ok`** — substituir o corpo de `dashboard(token)` por:

```python
def dashboard(token: str) -> None:
    me = api("GET", "/athletes/me", token=token).json()
    st.sidebar.success(f"Conectado: {me.get('full_name', '')}")
    if st.sidebar.button("Sair"):
        st.session_state.pop("token", None)
        st.rerun()

    _sample_workouts_sidebar(token)

    prof = api("GET", "/athletes/me/profile", token=token)
    profile = (prof.json() or {}) if prof.status_code == 200 else {}
    anamnese_ok = _anamnese_complete(profile)
    if not anamnese_ok:
        st.warning("Complete sua anamnese (aba 🩺 Anamnese) para liberar as recomendações.")

    tab_anamnese, tab_load, tab_import, tab_races, tab_plan, tab_rec = st.tabs(
        ["🩺 Anamnese", "📈 Forma & Carga", "📥 Importar", "🏁 Provas", "📅 Plano", "🧠 Recomendações"]
    )
    with tab_anamnese:
        anamnese_tab(token)
    with tab_load:
        load_tab(token)
    with tab_import:
        import_tab(token)
    with tab_races:
        races_tab(token)
    with tab_plan:
        plan_tab(token)
    with tab_rec:
        recommendations_tab(token, anamnese_ok)
```

- [ ] **Step 3: Gate na aba Recomendações** — alterar a assinatura e o topo de `recommendations_tab`. Trocar `def recommendations_tab(token: str) -> None:` por `def recommendations_tab(token: str, anamnese_ok: bool = True) -> None:` e inserir, logo após `st.subheader("Recomendação de treino")`:

```python
    if not anamnese_ok:
        st.info("Complete sua anamnese (aba 🩺 Anamnese) para gerar recomendações.")
        return
```

- [ ] **Step 4: Checar sintaxe**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); print('syntax OK')"`
Expected: `syntax OK`

- [ ] **Step 5: Verificação ao vivo**

Rebuild (`docker compose up -d --build`), logar como `athlete1` → aviso de anamnese + aba "🩺 Anamnese" como primeira; Recomendações mostra o aviso. Preencher e salvar a anamnese → aviso some e Recomendações libera.
Expected: gate funciona; anamnese salva.

- [ ] **Step 6: Commit**

```bash
git add frontend/app.py
git commit -m "feat(frontend): anamnese tab + onboarding gate on recommendations"
```

---

### Task 4: Frontend — aba "📝 Check-in diário"

**Files:**
- Modify: `frontend/app.py`

**Interfaces:**
- Consumes: `api(...)`, `date`, `dashboard`.
- Produces: `checkin_tab(token)`; `dashboard` monta a aba Check-in.

- [ ] **Step 1: Adicionar a aba** — inserir imediatamente antes de `def dashboard(token: str) -> None:`:

```python
def checkin_tab(token: str) -> None:
    st.subheader("📝 Check-in diário")
    st.caption("Como você está hoje? Isso ajusta a recomendação ao seu estado atual.")
    with st.form("checkin"):
        sleep_hours = st.number_input("Horas de sono", 0.0, 14.0, 7.0, step=0.5)
        resting_hr = st.number_input("FC repouso hoje", 30, 120, 55)
        hrv_ms = st.number_input("HRV (ms, opcional; 0 = não informar)", 0.0, 250.0, 0.0, step=1.0)
        fatigue = st.slider("Fadiga (1 ótimo – 5 exausto)", 1, 5, 3)
        soreness = st.slider("Dor muscular (1 – 5)", 1, 5, 2)
        mood = st.slider("Humor (1 – 5)", 1, 5, 4)
        motivation = st.slider("Motivação (1 – 5)", 1, 5, 4)
        injury_flag = st.checkbox("Dor/lesão hoje")
        comment = st.text_area("Comentário")
        if st.form_submit_button("Registrar check-in"):
            today = date.today().isoformat()
            rec = api("POST", "/metrics/recovery", token=token, json={
                "metric_date": today, "sleep_hours": sleep_hours,
                "resting_hr": int(resting_hr), "hrv_ms": hrv_ms or None,
            })
            sub = api("POST", "/metrics/subjective", token=token, json={
                "metric_date": today, "fatigue": fatigue, "soreness": soreness,
                "mood": mood, "motivation": motivation, "injury_flag": injury_flag,
                "comment": comment or None,
            })
            if rec.status_code == 201 and sub.status_code == 201:
                st.success("Check-in registrado. A próxima recomendação considerará seu estado de hoje.")
            else:
                st.error(f"recovery={rec.status_code} subjective={sub.status_code}")
```

- [ ] **Step 2: Montar a aba** — substituir o bloco de tabs em `dashboard(token)` por (adiciona "📝 Check-in" após Importar):

```python
    tab_anamnese, tab_load, tab_import, tab_checkin, tab_races, tab_plan, tab_rec = st.tabs(
        ["🩺 Anamnese", "📈 Forma & Carga", "📥 Importar", "📝 Check-in", "🏁 Provas", "📅 Plano", "🧠 Recomendações"]
    )
    with tab_anamnese:
        anamnese_tab(token)
    with tab_load:
        load_tab(token)
    with tab_import:
        import_tab(token)
    with tab_checkin:
        checkin_tab(token)
    with tab_races:
        races_tab(token)
    with tab_plan:
        plan_tab(token)
    with tab_rec:
        recommendations_tab(token, anamnese_ok)
```

- [ ] **Step 3: Checar sintaxe**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); print('syntax OK')"`
Expected: `syntax OK`

- [ ] **Step 4: Verificação ao vivo (gate de aceitação do loop)**

Com a anamnese preenchida (Task 3): aba "📝 Check-in" → registrar estado do dia (201/201) → gerar recomendação na aba Recomendações e conferir que o texto reflete perfil + estado (não mais genérico).
Expected: check-in registra; recomendação personalizada.

- [ ] **Step 5: Commit**

```bash
git add frontend/app.py
git commit -m "feat(frontend): daily readiness check-in tab"
```

---

## Self-Review (autor do plano)

- **Cobertura do spec:** §3.1 modelo/migração → Task 1; §3.2 injeção no prompt → Task 2 (Steps 3-5); §3.3 gate 409 → Task 2 (Step 6); §4.1 aba Anamnese + gate → Task 3; §4.2 aba Check-in → Task 4. Campos obrigatórios idênticos em `profile_context.REQUIRED_FIELDS` (back) e `_ANAMNESE_REQUIRED` (front).
- **Placeholders:** nenhum; código completo e comandos exatos. O único "pare e reporte" (Task 2 Step 7) é deliberado: o novo gate pode quebrar testes existentes que pedem recomendação sem anamnese — decisão do controlador, não do implementer.
- **Consistência de tipos/nomes:** `fetch_profile`/`anamnese_complete`/`profile_summary` definidos na Task 2 e usados no recomendador/endpoint; `render_daily_workout(..., profile=...)` casa com a chamada no recomendador; `recommendations_tab(token, anamnese_ok)` (Task 3) casa com as chamadas em `dashboard` (Tasks 3 e 4); `date` já importado no `app.py`; campos do PUT batem com `AthleteProfileBase` da Task 1.
