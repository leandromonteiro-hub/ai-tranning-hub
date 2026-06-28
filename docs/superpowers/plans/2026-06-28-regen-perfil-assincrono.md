# Regeneração de Perfil Assíncrona (Celery) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mover a regeneração pesada do perfil (`generate_and_persist_profile`) do caminho de request para uma task Celery, com endpoint de status do job e trava Redis por atleta.

**Architecture:** Novo job `profile_job.py` (espelha `import_job.py`) protegido por trava Redis por atleta; os endpoints de upload e onboarding enfileiram via `.delay` e retornam `profile_task_id`; um endpoint `GET /jobs/{task_id}` expõe só o estado via `AsyncResult`; o frontend faz polling e recarrega o perfil no sucesso.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Celery 5.4 + Redis 7 (já no projeto), pytest/pytest-asyncio. Frontend Streamlit.

## Global Constraints

- A infra Celery/Redis JÁ existe (`app.jobs.celery_app`, serviço `worker`, padrão em `app.jobs.import_job`). NÃO recriar.
- Trava Redis por atleta usa `settings.redis_url` (db 0), nome `f"profile_regen:{athlete_id}"`, `blocking=False`, TTL 900s.
- O retorno da task é MÍNIMO (`status` + `n_workouts`) — nunca dados sensíveis (o result backend é observável).
- `GET /jobs/{task_id}` retorna SÓ `{task_id, state}` — nunca `result` (anti-vazamento cross-tenant). Auth exigida.
- `recompute_load_metrics` (PMC) PERMANECE inline no upload — só o perfil vai para o worker.
- Falha de enqueue (`.delay` lança) NUNCA derruba o import/onboarding → logar e `profile_task_id=None`.
- A task deve ser importável SEM broker rodando (o registro `celery.task` fica em try/except, como nos jobs existentes).
- Regen concorrente (lock já tomado) → `status="skipped"`, sem tocar o DB.
- Backend tests via Docker:
  `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -v"`
- Frontend tests via Docker:
  `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest -q"`

---

### Task 1: Job Celery `profile_job.py` + autodiscover

**Files:**
- Create: `backend/app/jobs/profile_job.py`
- Modify: `backend/app/jobs/celery_app.py:24` (autodiscover import)
- Test: `backend/app/tests/test_jobs/test_profile_job.py` (novo; criar `__init__.py` se a pasta não existir)

**Interfaces:**
- Consumes: `generate_and_persist_profile(session, ctx, athlete_id)` de `app.services.analysis.profile_service`; `run_async` de `app.jobs._run`; `settings.redis_url`.
- Produces: `_do_regenerate(athlete_id: str, tenant_id: str) -> dict` (async) e `regenerate_profile_task(athlete_id, tenant_id)` (registrado em Celery como `name="regenerate_profile"`).

- [ ] **Step 1: Write the failing test**

Criar `backend/app/tests/test_jobs/__init__.py` (vazio) e `backend/app/tests/test_jobs/test_profile_job.py`:

```python
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.jobs import profile_job

pytestmark = pytest.mark.asyncio


def _fake_redis(acquired: bool):
    """Fake aioredis client whose lock.acquire() returns `acquired`."""
    lock = MagicMock()
    lock.acquire = AsyncMock(return_value=acquired)
    lock.release = AsyncMock()
    client = MagicMock()
    client.lock = MagicMock(return_value=lock)
    client.aclose = AsyncMock()
    return client, lock


async def test_regenerate_runs_profile_when_lock_acquired():
    aid = str(uuid.uuid4())
    client, lock = _fake_redis(acquired=True)
    fake_session = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_session)
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch.object(profile_job.aioredis, "from_url", return_value=client), \
         patch.object(profile_job, "AsyncSessionLocal", return_value=cm), \
         patch.object(profile_job, "generate_and_persist_profile",
                      new=AsyncMock(return_value={"n_workouts": 42})) as gen:
        out = await profile_job._do_regenerate(aid, "tenant-1")
    gen.assert_awaited_once()
    fake_session.commit.assert_awaited_once()
    lock.release.assert_awaited_once()
    assert out == {"status": "done", "n_workouts": 42}


async def test_regenerate_skips_when_lock_taken():
    aid = str(uuid.uuid4())
    client, lock = _fake_redis(acquired=False)
    with patch.object(profile_job.aioredis, "from_url", return_value=client), \
         patch.object(profile_job, "generate_and_persist_profile",
                      new=AsyncMock()) as gen:
        out = await profile_job._do_regenerate(aid, "tenant-1")
    gen.assert_not_awaited()           # não toca o DB quando já há regen rodando
    lock.release.assert_not_awaited()  # não solta um lock que não pegou
    assert out["status"] == "skipped"


def test_task_is_importable_without_broker():
    # O módulo importa e expõe a função mesmo sem Celery/broker.
    assert callable(profile_job.regenerate_profile_task)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_jobs/test_profile_job.py -v"`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.jobs.profile_job'`

- [ ] **Step 3: Create the job module**

Criar `backend/app/jobs/profile_job.py`:

```python
"""Async profile-regeneration job (twin_seed / FTP / power curve / methodology).

Mirrors app.jobs.import_job. A per-athlete Redis lock prevents concurrent
regenerations from racing on FtpHistory/PowerCurvePoint inserts; a second
concurrent task is skipped (the first already recomputes the state)."""
from __future__ import annotations

import uuid

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.jobs._run import run_async
from app.models.enums import Role
from app.services.analysis.profile_service import generate_and_persist_profile

log = get_logger(__name__)

_LOCK_TTL_S = 900  # > task_time_limit; auto-expira se o worker morrer


async def _do_regenerate(athlete_id: str, tenant_id: str) -> dict:
    aid = uuid.UUID(athlete_id)
    ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)
    client = aioredis.from_url(settings.redis_url)
    lock = client.lock(f"profile_regen:{athlete_id}", timeout=_LOCK_TTL_S, blocking=False)
    acquired = await lock.acquire()
    if not acquired:
        log.info("profile_regen_skipped_locked", extra={"athlete_id": athlete_id})
        await client.aclose()
        return {"status": "skipped", "reason": "regen already running"}
    try:
        async with AsyncSessionLocal() as session:
            summary = await generate_and_persist_profile(session, ctx, aid)
            await session.commit()
        return {"status": "done", "n_workouts": summary["n_workouts"]}
    finally:
        try:
            await lock.release()
        except Exception:  # noqa: BLE001 — lock pode ter expirado; não mascarar o resultado
            pass
        await client.aclose()


def regenerate_profile_task(athlete_id: str, tenant_id: str) -> dict:
    return run_async(_do_regenerate(athlete_id, tenant_id))


# Register with Celery when the app is available.
try:
    from app.jobs.celery_app import celery

    regenerate_profile_task = celery.task(name="regenerate_profile")(regenerate_profile_task)  # type: ignore[assignment]
except Exception:  # noqa: BLE001 — importable without a running broker (e.g. tests)
    pass
```

- [ ] **Step 4: Register in autodiscover**

Em `backend/app/jobs/celery_app.py`, localizar a linha 24:

```python
from app.jobs import import_job, metrics_job  # noqa: E402,F401
```

Trocar por:

```python
from app.jobs import import_job, metrics_job, profile_job  # noqa: E402,F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_jobs/test_profile_job.py -v"`
Expected: PASS (3 testes)

- [ ] **Step 6: Commit**

```bash
git add backend/app/jobs/profile_job.py backend/app/jobs/celery_app.py backend/app/tests/test_jobs/
git commit -m "feat(jobs): regenerate_profile_task — regen de perfil async com lock Redis por atleta"
```

---

### Task 2: Endpoint de status `GET /jobs/{task_id}`

**Files:**
- Create: `backend/app/api/routes/jobs.py`
- Create: `backend/app/schemas/jobs.py`
- Modify: `backend/app/main.py:8-19` (import do router) e `:68-69` (registro)
- Test: `backend/app/tests/test_api/test_jobs.py` (novo)

**Interfaces:**
- Consumes: `celery` de `app.jobs.celery_app`; `get_tenant` de `app.api.deps`.
- Produces: `JobStatus{task_id: str, state: str}`; rota `GET {api_prefix}/jobs/{task_id}`.

- [ ] **Step 1: Write the failing test**

Criar `backend/app/tests/test_api/test_jobs.py`. **Copie o bloco de fixture `env` + helper `_token` VERBATIM de `backend/app/tests/test_api/test_day_adjustment.py` (linhas 40-95)** — o projeto repete esse harness por arquivo de teste de API (SQLite in-memory, atletas `a@example.com`/`b@example.com`, senha `pw12345678`, prefixo `/api/v1`). Depois acrescente:

```python
from unittest.mock import MagicMock, patch


async def test_job_status_returns_state_only(env):
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    fake = MagicMock(state="SUCCESS", result={"secret": "should-not-leak"})
    with patch("app.api.routes.jobs.AsyncResult", return_value=fake):
        resp = await env.client.get("/api/v1/jobs/abc-123", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"task_id": "abc-123", "state": "SUCCESS"}
    assert "result" not in body  # nunca expõe o payload do resultado


async def test_job_status_requires_auth(env):
    resp = await env.client.get("/api/v1/jobs/abc-123")  # sem header
    assert resp.status_code in (401, 403)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_jobs.py -v"`
Expected: FAIL — rota inexistente (404) ou ImportError do módulo `jobs`.

- [ ] **Step 3: Create the schema**

Criar `backend/app/schemas/jobs.py`:

```python
"""Schema for the async job-status endpoint."""
from __future__ import annotations

from pydantic import BaseModel


class JobStatus(BaseModel):
    task_id: str
    state: str  # PENDING / STARTED / SUCCESS / FAILURE / RETRY
```

- [ ] **Step 4: Create the router**

Criar `backend/app/api/routes/jobs.py`:

```python
"""Async job-status endpoint (Celery AsyncResult — state only)."""
from __future__ import annotations

from celery.result import AsyncResult
from fastapi import APIRouter, Depends

from app.api.deps import get_tenant
from app.core.tenant import TenantContext
from app.jobs.celery_app import celery
from app.schemas.jobs import JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{task_id}", response_model=JobStatus)
async def job_status(
    task_id: str,
    ctx: TenantContext = Depends(get_tenant),
) -> JobStatus:
    """Return only the Celery task state. Never the result payload — the task_id
    is an opaque UUID and the state leaks nothing cross-tenant; the client
    re-fetches its own tenant-scoped profile (via /athletes/me/intelligence)
    on SUCCESS."""
    res = AsyncResult(task_id, app=celery)
    return JobStatus(task_id=task_id, state=res.state)
```

- [ ] **Step 5: Register the router in main.py**

Em `backend/app/main.py`, adicionar `jobs` ao import (linhas 8-19) em ordem alfabética:

```python
from app.api.routes import (
    admin,
    athletes,
    auth,
    feedback,
    imports,
    jobs,
    metrics,
    plans,
    races,
    recommendations,
    workouts,
)
```

E ao loop de registro (linhas 68-69):

```python
for r in (auth, athletes, workouts, metrics, imports, races, plans,
          recommendations, feedback, admin, jobs):
    app.include_router(r.router, prefix=_p)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_jobs.py -v"`
Expected: PASS (2 testes)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/jobs.py backend/app/schemas/jobs.py backend/app/main.py backend/app/tests/test_api/test_jobs.py
git commit -m "feat(api): GET /jobs/{task_id} — estado do job Celery (sem payload)"
```

---

### Task 3: Upload assíncrono + `UploadResponse`

**Files:**
- Modify: `backend/app/schemas/workout.py` (adicionar `UploadResponse`)
- Modify: `backend/app/api/routes/imports.py` (`upload_files` + imports)
- Test: `backend/app/tests/test_api/test_upload_async.py` (novo)

**Interfaces:**
- Consumes: `regenerate_profile_task` de `app.jobs.profile_job` (Task 1).
- Produces: `UploadResponse{files: list[ImportedFileRead], profile_task_id: str | None}`; `POST /imports/upload` retorna `UploadResponse`.

- [ ] **Step 1: Write the failing test**

Criar `backend/app/tests/test_api/test_upload_async.py`. **Copie o bloco de fixture `env` + helper `_token` VERBATIM de `test_day_adjustment.py` (linhas 40-95).** Para isolar o teste da fiação de enqueue (e não do parser de CSV), **mocka o pipeline** `import_file` e `recompute_load_metrics`. Acrescente:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def _fake_import_result(workouts_created: int):
    imported = SimpleNamespace(id="11111111-1111-1111-1111-111111111111",
                               status=SimpleNamespace(value="COMPLETED"))
    return SimpleNamespace(imported_file=imported, workouts_created=workouts_created)


async def test_upload_enqueues_profile_regen_and_returns_task_id(env):
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    task = MagicMock(id="task-xyz")
    with patch("app.api.routes.imports.import_file",
               new=AsyncMock(return_value=_fake_import_result(1))), \
         patch("app.api.routes.imports.recompute_load_metrics", new=AsyncMock()), \
         patch("app.api.routes.imports.regenerate_profile_task") as t:
        t.delay.return_value = task
        resp = await env.client.post(
            "/api/v1/imports/upload", headers=h,
            files=[("files", ("ride.csv", b"x", "text/csv"))],
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "files" in body
    assert body["profile_task_id"] == "task-xyz"
    t.delay.assert_called_once()  # enfileirou o regen (não rodou inline)


async def test_upload_no_new_workouts_does_not_enqueue(env):
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    with patch("app.api.routes.imports.import_file",
               new=AsyncMock(return_value=_fake_import_result(0))), \
         patch("app.api.routes.imports.recompute_load_metrics", new=AsyncMock()), \
         patch("app.api.routes.imports.regenerate_profile_task") as t:
        resp = await env.client.post(
            "/api/v1/imports/upload", headers=h,
            files=[("files", ("ride.csv", b"x", "text/csv"))],
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["profile_task_id"] is None
    t.delay.assert_not_called()  # 0 workouts novos → sem enqueue


async def test_upload_enqueue_failure_does_not_break_import(env):
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    with patch("app.api.routes.imports.import_file",
               new=AsyncMock(return_value=_fake_import_result(1))), \
         patch("app.api.routes.imports.recompute_load_metrics", new=AsyncMock()), \
         patch("app.api.routes.imports.regenerate_profile_task") as t:
        t.delay.side_effect = RuntimeError("broker down")
        resp = await env.client.post(
            "/api/v1/imports/upload", headers=h,
            files=[("files", ("ride.csv", b"x", "text/csv"))],
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["profile_task_id"] is None  # degrada, import preservado
```

NOTE p/ o implementer: `import_file`/`recompute_load_metrics` são mockados para focar o teste na fiação de enqueue (o pipeline real é coberto em `test_ingestion`/`test_metrics`). Se o `ImportedFileRead.model_validate` reclamar do `SimpleNamespace` fake, ajuste `_fake_import_result` para um objeto com os campos que `ImportedFileRead` exige (veja o schema) — ou um modelo `ImportedFile` real mínimo.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_upload_async.py -v"`
Expected: FAIL — resposta ainda é uma lista (sem `profile_task_id`) / `regenerate_profile_task` não importado em imports.

- [ ] **Step 3: Add the UploadResponse schema**

Em `backend/app/schemas/workout.py`, adicionar (após `ImportedFileRead`):

```python
class UploadResponse(BaseModel):
    """Response for POST /imports/upload: imported files + the async profile
    regeneration task id (None when no regen was enqueued)."""

    files: list[ImportedFileRead]
    profile_task_id: str | None = None
```

(Se `BaseModel` ainda não estiver importado no arquivo, adicionar `from pydantic import BaseModel` ao topo — verifique os imports existentes antes.)

- [ ] **Step 4: Rewrite upload_files to enqueue**

Em `backend/app/api/routes/imports.py`:

(a) Ajustar imports — remover o uso inline do profile e importar a task + o schema. Trocar a linha 22:

```python
from app.services.analysis.profile_service import generate_and_persist_profile
```

por:

```python
from app.jobs.profile_job import regenerate_profile_task
```

E na importação de schemas (linha 21) adicionar `UploadResponse`:

```python
from app.schemas.workout import ImportedFileRead, UploadResponse
```

(b) Trocar o decorator (linha 31) e o corpo do `upload_files` (linhas 31-66). O bloco atual:

```python
@router.post("/upload", response_model=list[ImportedFileRead])
async def upload_files(
    files: list[UploadFile] = File(...),
    source: str | None = Query(default="manual"),
    recompute: bool = Query(default=True),
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """..."""
    results = []
    workouts_created = 0
    for f in files:
        data = await f.read()
        result = await import_file(
            db, ctx, ctx.athlete_id, f.filename or "upload.bin", data, source=source
        )
        results.append(result.imported_file)
        workouts_created += result.workouts_created

    if recompute:
        await recompute_load_metrics(db, ctx, ctx.athlete_id)
        # Keep the reverse-engineered profile ... never fail the import itself.
        if workouts_created > 0:
            try:
                await generate_and_persist_profile(db, ctx, ctx.athlete_id)
            except Exception:
                log.exception("profile refresh after upload failed; import kept")

    return [ImportedFileRead.model_validate(r) for r in results]
```

passa a:

```python
@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
    source: str | None = Query(default="manual"),
    recompute: bool = Query(default=True),
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """..."""
    results = []
    workouts_created = 0
    for f in files:
        data = await f.read()
        result = await import_file(
            db, ctx, ctx.athlete_id, f.filename or "upload.bin", data, source=source
        )
        results.append(result.imported_file)
        workouts_created += result.workouts_created

    profile_task_id: str | None = None
    if recompute:
        # PMC (load metrics) stays inline — it's light. Only the heavy profile
        # regeneration (twin_seed / FTP / power curve) is offloaded to the worker.
        await recompute_load_metrics(db, ctx, ctx.athlete_id)
        await db.commit()
        if workouts_created > 0:
            # Enqueue is best-effort: a broker outage must never fail the import.
            try:
                task = regenerate_profile_task.delay(str(ctx.athlete_id), ctx.tenant_id)
                profile_task_id = task.id
            except Exception:
                log.exception("profile regen enqueue failed; import kept")

    return UploadResponse(
        files=[ImportedFileRead.model_validate(r) for r in results],
        profile_task_id=profile_task_id,
    )
```

NOTE: o `await db.commit()` é OBRIGATÓRIO aqui — o worker abre sua PRÓPRIA sessão e só enxerga dados já commitados; sem o commit antes do `.delay()`, o regen correria contra dados invisíveis. O `get_db` também commita no fim do request (double-commit é inócuo — o segundo é no-op). NÃO omita este commit.

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_upload_async.py -v"`
Expected: PASS (3 testes)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/imports.py backend/app/schemas/workout.py backend/app/tests/test_api/test_upload_async.py
git commit -m "feat(api): upload enfileira regen de perfil async (UploadResponse + profile_task_id)"
```

---

### Task 4: Onboarding assíncrono + mudança de resposta

**Files:**
- Modify: `backend/app/schemas/onboarding.py` (`TrainingPeaksOnboardingResponse`)
- Modify: `backend/app/api/routes/imports.py` (`onboard_trainingpeaks_export`)
- Test: `backend/app/tests/test_api/test_plan_workout_export.py` ou o teste de onboarding existente — localizar e atualizar; se não houver, criar `backend/app/tests/test_api/test_onboarding_async.py`

**Interfaces:**
- Consumes: `regenerate_profile_task` (Task 1), já importado em `imports.py` (Task 3).
- Produces: `TrainingPeaksOnboardingResponse{ingestion: IngestionSummary, profile_task_id: str}` (sem `richness`/`profile`).

- [ ] **Step 1: Write the failing test**

Primeiro, **grep por `trainingpeaks-export` em `backend/app/tests/`** para achar o teste de onboarding existente. Se existir, atualize suas asserções para o novo contrato (esperar `profile_task_id`, NÃO esperar `profile`/`richness`) — preferir editar a criar. Se não existir, criar `backend/app/tests/test_api/test_onboarding_async.py`, **copiando o bloco de fixture `env` + `_token` VERBATIM de `test_day_adjustment.py` (linhas 40-95)**, e mockando o pipeline de ingestão:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ingestion.tp_export_importer import IngestionReport  # dataclass real


async def test_onboarding_enqueues_and_drops_profile(env):
    h = {"Authorization": f"Bearer {await _token(env.client, 'a@example.com')}"}
    task = MagicMock(id="onb-task-1")
    report = IngestionReport()  # todos os campos com default; ajuste se exigir args
    with patch("app.api.routes.imports.import_athlete_folder",
               new=AsyncMock(return_value=report)), \
         patch("app.api.routes.imports.regenerate_profile_task") as t:
        t.delay.return_value = task
        resp = await env.client.post(
            "/api/v1/imports/trainingpeaks-export", headers=h,
            files=[("files", ("export.zip", b"x", "application/zip"))],
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["profile_task_id"] == "onb-task-1"
    assert "ingestion" in body
    assert "profile" not in body      # perfil agora é async
    assert "richness" not in body
    t.delay.assert_called_once()
```

NOTE p/ o implementer: confirme a localização/nome real de `IngestionReport` (grep por `class IngestionReport`) e que ele instancia sem args (todos defaults); se exigir campos, passe valores mínimos. `import_athlete_folder` é mockado para focar o teste no novo contrato de resposta (a ingestão real é coberta em `test_ingestion`).

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api -k onboarding -v"`
Expected: FAIL — resposta ainda contém `profile`/`richness`, sem `profile_task_id`.

- [ ] **Step 3: Update the response schema**

Em `backend/app/schemas/onboarding.py`, trocar `TrainingPeaksOnboardingResponse` (linhas 54-65):

```python
class TrainingPeaksOnboardingResponse(BaseModel):
    """Response schema for POST /imports/trainingpeaks-export.

    Fields:
        ingestion: counts and coverage from import_athlete_folder (IngestionReport).
        profile_task_id: id of the async profile-regeneration Celery task; the
            client polls GET /jobs/{id} and fetches the profile via
            /athletes/me/intelligence on SUCCESS.
    """

    ingestion: IngestionSummary
    profile_task_id: str
```

(`RichnessSummary`/`ProfileSummary` ficam no módulo — podem ser usados em outros lugares; não removê-los aqui.)

- [ ] **Step 4: Rewrite onboard_trainingpeaks_export**

Em `backend/app/api/routes/imports.py`, o bloco Step 3-5 atual (linhas ~125-148):

```python
    # Step 3: Run the Task-2 analysis pipeline (idempotent) ...
    profile_summary = await generate_and_persist_profile(db, ctx, ctx.athlete_id)

    # Step 4: Commit.
    await db.commit()

    # Step 5: Build and return the response.
    ingestion_dict = dataclasses.asdict(ingestion_report)
    richness_dict = profile_summary["richness"]

    return TrainingPeaksOnboardingResponse(
        ingestion=IngestionSummary(**ingestion_dict),
        richness=RichnessSummary(**richness_dict),
        profile=ProfileSummary(
            n_workouts=profile_summary["n_workouts"],
            weeks=profile_summary["weeks"],
            ftp_recent=profile_summary["ftp_recent"],
            n_blocks=profile_summary["n_blocks"],
            n_races=profile_summary["n_races"],
            excluded_power_streams=profile_summary["excluded_power_streams"],
            richness=richness_dict,
        ),
    )
```

passa a:

```python
    # Step 3: Commit the ingestion so the async worker (own session) sees it.
    await db.commit()

    # Step 4: Enqueue the heavy profile regeneration (best-effort).
    profile_task_id = ""
    try:
        task = regenerate_profile_task.delay(str(ctx.athlete_id), ctx.tenant_id)
        profile_task_id = task.id
    except Exception:
        log.exception("profile regen enqueue failed; onboarding ingestion kept")

    # Step 5: Build and return the response (profile arrives async).
    ingestion_dict = dataclasses.asdict(ingestion_report)
    return TrainingPeaksOnboardingResponse(
        ingestion=IngestionSummary(**ingestion_dict),
        profile_task_id=profile_task_id,
    )
```

(b) Limpar imports agora não usados em `imports.py`: remover `ProfileSummary` e `RichnessSummary` da importação de `app.schemas.onboarding` (linhas 15-20) — manter `IngestionSummary` e `TrainingPeaksOnboardingResponse`. Verifique se `generate_and_persist_profile` ainda é referenciado em algum lugar do arquivo; após Tasks 3-4 não deve ser — se o import já foi trocado na Task 3, não há o que remover aqui.

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api -k onboarding -v"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/imports.py backend/app/schemas/onboarding.py backend/app/tests/test_api/
git commit -m "feat(api): onboarding enfileira regen async (resposta troca profile por profile_task_id)"
```

---

### Task 5: Frontend — polling helper + import_tab

**Files:**
- Create: `frontend/job_poll.py` (helper puro)
- Modify: `frontend/app.py` (`import_tab`, ~linhas 119-132)
- Test: `frontend/test_job_poll.py` (novo)

**Interfaces:**
- Consumes: a resposta `{files, profile_task_id}` do upload e `GET /jobs/{task_id}` → `{state}`.
- Produces: `poll_decision(state: str, attempt: int, max_attempts: int) -> str` retornando `"done" | "failed" | "giveup" | "continue"`.

- [ ] **Step 1: Write the failing test**

Criar `frontend/test_job_poll.py`:

```python
from job_poll import poll_decision


def test_poll_decision_done_on_success():
    assert poll_decision("SUCCESS", 1, 10) == "done"


def test_poll_decision_failed_on_failure():
    assert poll_decision("FAILURE", 1, 10) == "failed"


def test_poll_decision_continue_while_pending_under_cap():
    assert poll_decision("PENDING", 1, 10) == "continue"
    assert poll_decision("STARTED", 5, 10) == "continue"


def test_poll_decision_giveup_at_cap():
    assert poll_decision("PENDING", 10, 10) == "giveup"
    assert poll_decision("STARTED", 11, 10) == "giveup"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest test_job_poll.py -v"`
Expected: FAIL — `ModuleNotFoundError: No module named 'job_poll'`

- [ ] **Step 3: Create the pure helper**

Criar `frontend/job_poll.py`:

```python
"""Pure decision logic for polling an async job's Celery state.

Kept free of Streamlit/requests so it can be unit-tested. The caller does the
actual HTTP poll + sleep and feeds the state here each tick."""
from __future__ import annotations

_TERMINAL_OK = "SUCCESS"
_TERMINAL_FAIL = "FAILURE"


def poll_decision(state: str, attempt: int, max_attempts: int) -> str:
    """Return the next action given the job state and how many polls happened.

    - "done"     → state is SUCCESS
    - "failed"   → state is FAILURE
    - "giveup"   → not terminal but attempts reached the cap
    - "continue" → keep polling
    """
    if state == _TERMINAL_OK:
        return "done"
    if state == _TERMINAL_FAIL:
        return "failed"
    if attempt >= max_attempts:
        return "giveup"
    return "continue"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest test_job_poll.py -v"`
Expected: PASS (4 testes)

- [ ] **Step 5: Wire import_tab to the new response + polling**

Em `frontend/app.py`, no topo adicionar o import (junto aos demais imports de módulos locais):

```python
from job_poll import poll_decision
```

E trocar o corpo do `import_tab` (linhas 119-132). Bloco atual:

```python
def import_tab(token: str) -> None:
    st.subheader("Importar arquivos (CSV TrainingPeaks, FIT, TCX, GPX)")
    files = st.file_uploader(
        "Selecione arquivos", accept_multiple_files=True,
        type=["csv", "fit", "tcx", "gpx"],
    )
    if files and st.button("Enviar"):
        multipart = [("files", (f.name, f.getvalue())) for f in files]
        resp = api("POST", "/imports/upload", token=token, files=multipart)
        if resp.status_code == 200:
            st.success("Importação concluída")
            st.dataframe(pd.DataFrame(resp.json()))
        else:
            st.error(resp.text)
```

passa a:

```python
def import_tab(token: str) -> None:
    st.subheader("Importar arquivos (CSV TrainingPeaks, FIT, TCX, GPX)")
    files = st.file_uploader(
        "Selecione arquivos", accept_multiple_files=True,
        type=["csv", "fit", "tcx", "gpx"],
    )
    if files and st.button("Enviar"):
        multipart = [("files", (f.name, f.getvalue())) for f in files]
        resp = api("POST", "/imports/upload", token=token, files=multipart)
        if resp.status_code != 200:
            st.error(resp.text)
            return
        body = resp.json()
        st.success("Importação concluída")
        st.dataframe(pd.DataFrame(body.get("files", [])))

        task_id = body.get("profile_task_id")
        if task_id:
            _await_profile_regen(token, task_id)


def _await_profile_regen(token: str, task_id: str, max_attempts: int = 30) -> None:
    """Poll the async profile-regeneration job and report when the profile is fresh."""
    with st.spinner("🔄 Atualizando seu perfil…"):
        for attempt in range(1, max_attempts + 1):
            r = api("GET", f"/jobs/{task_id}", token=token)
            state = r.json().get("state", "PENDING") if r.status_code == 200 else "PENDING"
            decision = poll_decision(state, attempt, max_attempts)
            if decision == "done":
                st.success("Perfil atualizado.")
                return
            if decision == "failed":
                st.warning("O perfil será atualizado em instantes.")
                return
            if decision == "giveup":
                st.info("O perfil está sendo atualizado em segundo plano.")
                return
            time.sleep(1)
```

NOTE p/ o implementer: confirme que `time` está importado no topo de `app.py` (senão adicionar `import time`). Não mexer em outras abas.

- [ ] **Step 6: Run the full frontend suite**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest -q"`
Expected: PASS (incl. os 4 novos de `job_poll`).

- [ ] **Step 7: Commit**

```bash
git add frontend/job_poll.py frontend/app.py frontend/test_job_poll.py
git commit -m "feat(frontend): polling do regen de perfil async no import_tab"
```

---

### Task 6: Regressão + suítes completas

**Files:**
- Test: `backend/app/tests/` (suíte inteira) + frontend

**Interfaces:**
- Consumes: tudo das Tasks 1-5.
- Produces: confirmação de que nenhum chamador inline de `generate_and_persist_profile` ficou no caminho de request e que as suítes estão verdes.

- [ ] **Step 1: Grep por regen inline remanescente**

Usar o Grep tool: procurar `generate_and_persist_profile` em `backend/app` (excluindo testes/scripts/services).
Expected: aparece em `services/analysis/profile_service.py` (definição), no novo `jobs/profile_job.py` (uso async) e em `scripts/analyze_athlete.py` (CLI — ok). NÃO deve aparecer mais em `api/routes/imports.py`. Confirmar.

- [ ] **Step 2: Run the API + jobs suites**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api app/tests/test_jobs -v"`
Expected: PASS (0 failures).

- [ ] **Step 3: Run the full backend suite**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest -q"`
Expected: exit 0. Anotar pass count + warnings (esperado: só o `passlib/crypt` pré-existente). Atenção a testes de onboarding antigos que ainda assertem `profile`/`richness` na resposta — se algum quebrar, é um teste desatualizado pelo novo contrato: atualizá-lo (não reverter o contrato).

- [ ] **Step 4: Run the full frontend suite**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest -q"`
Expected: PASS.

- [ ] **Step 5: Commit (se houver ajuste residual)**

Se Steps 1-4 expuserem um teste desatualizado pelo novo contrato (onboarding antigo), corrigir e:

```bash
git add -A
git commit -m "test(api): alinha testes de onboarding ao contrato async (profile_task_id)"
```

Se nada extra for necessário, pular este commit.

---

## Self-Review

**Spec coverage:**
- Job `profile_job.py` + lock Redis + autodiscover → Task 1 ✓
- Status endpoint `GET /jobs/{task_id}` (state only) → Task 2 ✓
- Upload async + `UploadResponse` + PMC inline + enqueue best-effort → Task 3 ✓
- Onboarding async + resposta dropa profile/richness + `profile_task_id` → Task 4 ✓
- Frontend polling (helper puro + import_tab) → Task 5 ✓
- Regressão (sem regen inline remanescente; suítes) → Task 6 ✓
- Critérios de aceite 1-7 → Tasks 1-6 ✓
- Concorrência (lock, skip sem tocar DB) → Task 1 testes ✓
- Anti-vazamento cross-tenant (state only) → Task 2 teste `result not in body` ✓

**Placeholder scan:** sem TBD/TODO; todo passo de código mostra código exato. Os testes de API referenciam um harness CONCRETO (copiar `env` + `_token` de `test_day_adjustment.py` linhas 40-95, prefixo `/api/v1`, atletas `a@example.com`/`pw12345678`) — não há fixture hipotética. As NOTEs restantes são checagens de integração pontuais (campos de `ImportedFileRead`, assinatura de `IngestionReport`) que o implementer confirma lendo o schema/dataclass — necessárias porque o plano não inclui esses arquivos na íntegra.

**Type consistency:** `regenerate_profile_task.delay(str(athlete_id), tenant_id)` chamado idêntico em Tasks 3 e 4, definido em Task 1; `_do_regenerate(athlete_id: str, tenant_id: str) -> dict` consistente; `UploadResponse{files, profile_task_id}` consistente entre schema (Task 3) e teste; `JobStatus{task_id, state}` consistente entre Task 2 schema/rota/teste; `poll_decision(state, attempt, max_attempts) -> str` consistente entre Task 5 helper, teste e uso em `_await_profile_regen`; `TrainingPeaksOnboardingResponse{ingestion, profile_task_id}` consistente entre Task 4 schema/endpoint/teste.

**Risco conhecido sinalizado:** Tasks 3 e 4 ambas editam `imports.py` — devem rodar em ordem (3 antes de 4); a Task 4 assume o import de `regenerate_profile_task` já feito na Task 3. O `await db.commit()` extra na Task 3/4 tem uma NOTE pedindo verificação de double-commit contra `import_file`/`recompute_load_metrics`.
