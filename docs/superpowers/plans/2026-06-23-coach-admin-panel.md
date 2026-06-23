# Coach/Admin Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quando um ADMIN loga, mostrar um painel de monitoramento da validação (métricas, atletas, feedbacks atribuídos ao atleta), com o feedback do backend passando a carregar `athlete_id`.

**Architecture:** Mudança mínima de backend (1 campo no schema `FeedbackRead`, coberta por teste pytest) + nova tela no frontend Streamlit (`admin_dashboard` + detecção de papel em `main`). Sem novas rotas — consome `GET /admin/usage|athletes|feedback` já existentes (protegidas por `require_admin`).

**Tech Stack:** FastAPI/Pydantic v2 (backend), Streamlit + httpx + pandas (frontend), pytest (backend test). Frontend sem testes de UI (padrão) — `ast.parse` + verificação ao vivo.

## Global Constraints

- **Backend:** única mudança é expor `athlete_id: uuid.UUID` em `FeedbackRead` (`backend/app/schemas/ai.py`). Nenhuma rota/query muda (o modelo já tem `athlete_id` via `TenantMixin`).
- **Frontend:** ADMIN (`role == "ADMIN"` em `/athletes/me`) → `admin_dashboard(token)`; senão `dashboard(token)` atual. Tudo via helper `api()`. Leituras com fallback a `[]`/`{}` quando `status_code != 200`. Estados vazios tratados. Painel é só leitura (sem `st.rerun()` exceto no logout).
- **Comando de teste backend (da raiz do repo):**
  `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <caminho> -v"`
- **Comando de sintaxe frontend (da raiz do repo):**
  `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); print('syntax OK')"`
- Commits frequentes, um por task.

---

### Task 1: Atribuir feedback ao atleta (`athlete_id` no `FeedbackRead`)

**Files:**
- Modify: `backend/app/schemas/ai.py` (classe `FeedbackRead`)
- Test: `backend/app/tests/test_api/test_admin_panel.py` (novo)

**Interfaces:**
- Consumes: rotas existentes `POST /recommendations`, `POST /feedback/{rec_id}`, `GET /admin/feedback`, `GET /athletes/me`, `POST /auth/login`.
- Produces: `FeedbackRead` passa a incluir `athlete_id: uuid.UUID`; `GET /admin/feedback` retorna esse campo por item.

- [ ] **Step 1: Escrever o teste que falha** — criar `backend/app/tests/test_api/test_admin_panel.py`:

```python
"""Admin panel: the feedback feed attributes each feedback to its athlete."""
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
async def client_admin():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        s.add_all([
            Athlete(email="admin@example.com", hashed_password=hash_password("pw12345678"),
                    full_name="Admin", role=Role.ADMIN, tenant_id="tadmin"),
            Athlete(email="a@example.com", hashed_password=hash_password("pw12345678"),
                    full_name="Atleta A", role=Role.ATHLETE, tenant_id="ta"),
        ])
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


async def test_admin_feedback_includes_athlete_id(client_admin):
    ath = {"Authorization": f"Bearer {await _login(client_admin, 'a@example.com')}"}
    me = (await client_admin.get("/api/v1/athletes/me", headers=ath)).json()
    athlete_id = me["id"]

    rec = await client_admin.post("/api/v1/recommendations", headers=ath,
                                  json={"kind": "daily_workout"})
    assert rec.status_code == 201, rec.text
    rec_id = rec.json()["id"]
    fb = await client_admin.post(f"/api/v1/feedback/{rec_id}", headers=ath,
                                 json={"rating": 5, "made_sense": True, "comment": "ok"})
    assert fb.status_code == 201, fb.text

    adm = {"Authorization": f"Bearer {await _login(client_admin, 'admin@example.com')}"}
    res = await client_admin.get("/api/v1/admin/feedback", headers=adm)
    assert res.status_code == 200, res.text
    items = res.json()
    assert len(items) >= 1
    assert items[0]["athlete_id"] == athlete_id
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_admin_panel.py -v"`
Expected: FAIL no `assert items[0]["athlete_id"] == athlete_id` (`KeyError: 'athlete_id'`, pois o campo ainda não é exposto).

- [ ] **Step 3: Adicionar o campo** — em `backend/app/schemas/ai.py`, na classe `FeedbackRead`, adicionar `athlete_id` logo após `recommendation_id`:

```python
class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    recommendation_id: uuid.UUID
    athlete_id: uuid.UUID
    rating: int
    made_sense: bool | None = None
    observed_result: str | None = None
    comment: str | None = None
    created_at: datetime
```

(`uuid` e `datetime` já estão importados no arquivo.)

- [ ] **Step 4: Rodar para ver passar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_admin_panel.py -v"`
Expected: PASS.

- [ ] **Step 5: Rodar a suíte completa (sem regressões)**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest -q"`
Expected: PASS (atuais 72 + o novo).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/ai.py backend/app/tests/test_api/test_admin_panel.py
git commit -m "feat(api): expose athlete_id on FeedbackRead for the admin feed"
```

---

### Task 2: Painel do treinador no frontend (`admin_dashboard` + detecção de papel)

**Files:**
- Modify: `frontend/app.py`

**Interfaces:**
- Consumes: `api(...)`, `pandas as pd` (já importados); `GET /admin/usage`, `GET /admin/athletes`, `GET /admin/feedback` (com `athlete_id` da Task 1); `GET /athletes/me` (campo `role`).
- Produces: `admin_dashboard(token)`; `main()` roteia por papel.

- [ ] **Step 1: Adicionar `admin_dashboard`** — inserir esta função imediatamente antes de `def main() -> None:` em `frontend/app.py`:

```python
def admin_dashboard(token: str) -> None:
    st.sidebar.success("Treinador (admin)")
    if st.sidebar.button("Sair"):
        st.session_state.pop("token", None)
        st.rerun()

    st.title("📋 Painel do treinador — validação")

    usage = api("GET", "/admin/usage", token=token)
    u = usage.json() if usage.status_code == 200 else {}
    st.subheader("📊 Métricas da validação")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Atletas", u.get("athletes", 0))
    c2.metric("Treinos", u.get("workouts", 0))
    c3.metric("Recomendações", u.get("recommendations", 0))
    c4.metric("Feedbacks", u.get("feedback_count", 0))
    c5.metric("Nota média", f"{u.get('avg_feedback_rating', 0):.1f}")

    ath_resp = api("GET", "/admin/athletes", token=token)
    athletes = ath_resp.json() if ath_resp.status_code == 200 else []
    names = {a["id"]: a["full_name"] for a in athletes}

    st.subheader("👥 Atletas")
    if athletes:
        st.dataframe(pd.DataFrame([
            {"Nome": a["full_name"], "Email": a["email"],
             "Ativo": "✅" if a.get("is_active") else "—"}
            for a in athletes
        ]), hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum atleta.")

    st.subheader("💬 Feedbacks")
    fb_resp = api("GET", "/admin/feedback", token=token)
    feedbacks = fb_resp.json() if fb_resp.status_code == 200 else []
    if feedbacks:
        st.dataframe(pd.DataFrame([
            {"Atleta": names.get(f.get("athlete_id"), str(f.get("athlete_id"))[:8]),
             "Nota": f.get("rating"),
             "Fez sentido": "✅" if f.get("made_sense") else "—",
             "Comentário": f.get("comment") or "",
             "Data": (f.get("created_at") or "")[:10]}
            for f in feedbacks
        ]), hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum feedback ainda.")
```

- [ ] **Step 2: Rotear por papel** — substituir a função `main` por:

```python
def main() -> None:
    token = st.session_state.get("token")
    if not token:
        login_view()
        return
    me = api("GET", "/athletes/me", token=token).json()
    if me.get("role") == "ADMIN":
        admin_dashboard(token)
    else:
        dashboard(token)
```

- [ ] **Step 3: Checar sintaxe**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); print('syntax OK')"`
Expected: `syntax OK`

- [ ] **Step 4: Verificação ao vivo (gate de aceitação)**

Rebuild da stack (`docker compose up -d --build`), abrir http://localhost:8501, logar como **`admin@athletehub.example.com` / `admin_dev_pwd`** → ver o "📋 Painel do treinador" com: métricas (atletas/treinos/recomendações/feedbacks/nota média), tabela de atletas, e feed de feedbacks **com o nome do atleta**. Logar como `athlete1@athletehub.example.com` → continua vendo o dashboard de atleta normal.
Expected: admin vê o painel; atleta vê o dashboard de sempre.

- [ ] **Step 5: Commit**

```bash
git add frontend/app.py
git commit -m "feat(frontend): coach/admin monitoring dashboard (metrics, athletes, feedback)"
```

---

## Self-Review (autor do plano)

- **Cobertura do spec:** §3 (athlete_id no FeedbackRead + teste) → Task 1; §4.1 detecção de papel → Task 2 Step 2; §4.2 (`admin_dashboard`: métricas/atletas/feedbacks atribuídos) → Task 2 Step 1; §5 erros/estados-vazios → fallbacks `[]`/`{}` e `st.info` em cada seção; §6 testes → Task 1 (pytest) + Task 2 (ast.parse + live).
- **Placeholders:** nenhum; cada step tem código completo e comandos exatos.
- **Consistência de tipos/nomes:** `athlete_id` exposto na Task 1 é consumido por `f.get("athlete_id")` na Task 2; `names = {a["id"]: a["full_name"]}` cruza com `athlete_id`; chaves de `/admin/usage` (`athletes`, `workouts`, `recommendations`, `feedback_count`, `avg_feedback_rating`) batem com o endpoint real; `me.get("role") == "ADMIN"` bate com `AthleteRead.role` (enum `Role.ADMIN` serializa como `"ADMIN"`).
