# Spec — Regeneração de perfil assíncrona (Celery)

**Data:** 2026-06-28
**Stream:** Training Intelligence Layer · escala pré-comercial
**Status:** aprovado (brainstorming), pronto para plano de implementação

## Problema

A regeneração do perfil reverso (`twin_seed` / FTP / curva de potência / metodologia,
via `generate_and_persist_profile`) roda **inline** no caminho de request em dois
endpoints: `POST /imports/upload` (após o import incremental) e
`POST /imports/trainingpeaks-export` (onboarding). É a parte mais pesada do
pipeline e bloqueia a resposta HTTP. Antes de escalar além dos 2 atletas de
validação, mover esse trabalho para o worker Celery (infra já existente:
`redis`, serviço `worker`, `app.jobs.celery_app`, padrão em `app.jobs.import_job`,
hoje dormente no caminho de request).

## Objetivo

Enfileirar a regeneração do perfil como uma task Celery em ambos os endpoints; a
resposta HTTP volta imediatamente com um `profile_task_id`. O cliente acompanha a
conclusão por um endpoint de status do job e, no sucesso, busca o perfil
atualizado pelo `/athletes/me/intelligence` existente (tenant-scoped). Uma trava
Redis por atleta evita regens concorrentes.

Fora de escopo: tornar `recompute_load_metrics` (PMC) assíncrono — fica inline,
é leve; só o regen pesado do perfil vai para o worker. Idempotência profunda de
`FtpHistory`/`PowerCurvePoint` (delete-then-insert) — coberta pragmaticamente pela
trava, não reescrita aqui.

## Decisões de design (do brainstorming)

1. **Escopo:** upload incremental **e** onboarding vão para async (ambos perdem o
   retorno síncrono do perfil; onboarding também perde `richness`).
2. **Sinal de pronto:** endpoint de status do job `GET /jobs/{task_id}` via
   `celery.AsyncResult`, retornando **só o estado** (sem payload do resultado, p/
   não vazar dados cross-tenant). O frontend faz polling.
3. **Concorrência:** trava Redis por `athlete_id` na task; um regen concorrente
   é descartado (o primeiro já recomputa o estado).
4. **Infra reusada:** Celery + Redis já existem; `settings.redis_url` (db 0) para
   a trava; padrão de job idêntico a `app.jobs.import_job`.

## Componentes

### 1. Task Celery — `backend/app/jobs/profile_job.py` (novo)

Espelha `import_job.py`. A trava Redis envolve o trabalho pesado:

```python
"""Async profile-regeneration job (twin_seed / FTP / power curve / methodology)."""
from __future__ import annotations

import uuid

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.tenant import TenantContext
from app.jobs._run import run_async
from app.models.enums import Role
from app.services.analysis.profile_service import generate_and_persist_profile

_LOCK_TTL_S = 900  # > task_time_limit; auto-expira se o worker morrer


async def _do_regenerate(athlete_id: str, tenant_id: str) -> dict:
    aid = uuid.UUID(athlete_id)
    ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)
    client = aioredis.from_url(settings.redis_url)
    lock = client.lock(f"profile_regen:{athlete_id}", timeout=_LOCK_TTL_S, blocking=False)
    acquired = await lock.acquire()
    if not acquired:
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


try:
    from app.jobs.celery_app import celery

    regenerate_profile_task = celery.task(name="regenerate_profile")(regenerate_profile_task)  # type: ignore[assignment]
except Exception:  # noqa: BLE001 — importável sem broker (testes)
    pass
```

Registrar no autodiscover: em `celery_app.py`, a linha
`from app.jobs import import_job, metrics_job` passa a incluir `profile_job`.

O retorno é **mínimo** (`status` + `n_workouts`) — nunca dados sensíveis, já que
o estado/resultado pode ser observável pelo result backend.

### 2. Endpoint de upload — `upload_files` (`api/routes/imports.py`)

Troca o regen inline por enqueue e muda o shape da resposta.

- Remover o bloco `try: await generate_and_persist_profile(...)`.
- Quando `recompute and workouts_created > 0`: enfileirar
  `task = regenerate_profile_task.delay(str(ctx.athlete_id), ctx.tenant_id)` e
  capturar `task.id`. Caso contrário `profile_task_id = None`.
- Resposta passa de `list[ImportedFileRead]` para um objeto novo
  `UploadResponse{ files: list[ImportedFileRead], profile_task_id: str | None }`.

`recompute_load_metrics` (PMC) **permanece inline** — só o perfil vai para o worker.

### 3. Endpoint de onboarding — `onboard_trainingpeaks_export`

- Remover `profile_summary = await generate_and_persist_profile(...)` e o
  `await db.commit()` que dependia dele passa a commitar só a ingestão.
- Enfileirar `task = regenerate_profile_task.delay(str(ctx.athlete_id), ctx.tenant_id)`.
- Resposta `TrainingPeaksOnboardingResponse` **dropa** `richness` e `profile`,
  mantém `ingestion`, ganha `profile_task_id: str`. (`richness`/`profile` vêm do
  regen → chegam depois, via intelligence.)

### 4. Endpoint de status — `GET /jobs/{task_id}` (router novo `api/routes/jobs.py`, registrado no app como os demais routers)

```python
from celery.result import AsyncResult
from app.jobs.celery_app import celery

@router.get("/jobs/{task_id}", response_model=JobStatus)
async def job_status(task_id: str, ctx: TenantContext = Depends(get_tenant)) -> JobStatus:
    res = AsyncResult(task_id, app=celery)
    return JobStatus(task_id=task_id, state=res.state)  # PENDING/STARTED/SUCCESS/FAILURE/RETRY
```

`JobStatus{ task_id: str, state: str }` — **só o estado**, sem `res.result`. Auth-gated
(qualquer atleta autenticado); o `task_id` é UUID opaco e o estado não revela
dados de outro tenant. No `SUCCESS`, o frontend busca o próprio perfil
tenant-scoped via `/athletes/me/intelligence`.

### 5. Frontend (Streamlit)

Nos dois fluxos (upload e onboarding), após receber `profile_task_id`:
- Mostrar "🔄 Atualizando seu perfil…".
- Fazer polling de `GET /jobs/{task_id}` (intervalo curto, com teto de tentativas).
- No `SUCCESS`: recarregar o painel de inteligência (já lê o perfil persistido).
- No `FAILURE` ou teto atingido: aviso não-bloqueante ("o perfil será atualizado
  em instantes") — o import/onboarding em si já teve sucesso.

### 6. Schemas — `backend/app/schemas/`

- `UploadResponse` (novo): `files: list[ImportedFileRead]`, `profile_task_id: str | None`.
- `JobStatus` (novo): `task_id: str`, `state: str`.
- `TrainingPeaksOnboardingResponse`: remover `richness` e `profile`; adicionar
  `profile_task_id: str`.

## Fluxo de dados

```
POST /imports/upload      → import_file (inline) → recompute PMC (inline)
                            → regenerate_profile_task.delay(aid, tenant)  → task_id
                            → 200 { files, profile_task_id }
                                                        │
worker: _do_regenerate → lock Redis(profile_regen:aid) ─┤ adquiriu? → generate_and_persist_profile → commit
                                                        └ não? → skip
frontend: poll GET /jobs/{task_id} → SUCCESS → GET /athletes/me/intelligence (perfil fresco)
```

## Tratamento de erros / degradação

- **Import nunca falha pelo perfil:** o regen agora é fora do request; o enqueue é
  best-effort, mas falhar o `.delay` (broker down) não deve derrubar o import —
  envolver o enqueue em try/except, logar, e retornar `profile_task_id=None`.
- **Regen concorrente:** segundo task pega `acquired=False` → retorna `skipped`
  (estado `SUCCESS` com payload skipped). O frontend trata `SUCCESS` igual.
- **Worker morre no meio:** a trava expira em `_LOCK_TTL_S` (900s); próximo upload
  reenfileira.
- **task_id inexistente/expirado:** `AsyncResult.state` retorna `PENDING` — o
  frontend tem teto de tentativas e degrada para o aviso não-bloqueante.
- **Falha do regen:** estado `FAILURE`; o perfil antigo persiste (o novo só é
  commitado em sucesso). Frontend avisa, não bloqueia.

## Testes

- **`_do_regenerate`** (contra DB de teste, sem worker): com lock livre, persiste o
  perfil e retorna `status="done"`; com lock já tomado (mock do `acquire→False`),
  retorna `status="skipped"` e **não** toca o DB.
- **`upload_files`:** com `workouts_created>0`, o endpoint chama
  `regenerate_profile_task.delay` com `(str(aid), tenant_id)` (mock do `.delay`,
  sem broker) e retorna `profile_task_id`; com `0` novos, não enfileira
  (`profile_task_id=None`); o import e o PMC ainda rodam inline. Isolamento por
  atleta preservado.
- **`onboard_trainingpeaks_export`:** enfileira e retorna `profile_task_id`;
  resposta não contém mais `profile`/`richness`; `ingestion` intacta.
- **Enqueue best-effort:** `.delay` lançando exceção não derruba o import (mock que
  levanta → 200 com `profile_task_id=None`).
- **`GET /jobs/{task_id}`:** com `AsyncResult` fake (mock) por estado, retorna
  `{task_id, state}` e **nunca** inclui `result`. Auth exigida.
- **Frontend:** a função de polling para em `SUCCESS`/`FAILURE` e respeita o teto;
  testar a lógica pura de decisão (continuar/parar) isolada de Streamlit.
- **Registro Celery:** `regenerate_profile_task` importável sem broker (o
  `try/except` de registro não explode em import).

## Critérios de aceite

1. Ambos os endpoints enfileiram o regen e retornam `profile_task_id`; nenhum
   roda `generate_and_persist_profile` inline.
2. `recompute_load_metrics` continua inline no upload.
3. `GET /jobs/{task_id}` retorna só `{task_id, state}` (sem payload do resultado).
4. A task usa trava Redis por atleta; regen concorrente é descartado.
5. Falha de enqueue/regen nunca derruba o import/onboarding.
6. Frontend faz polling e recarrega o perfil no sucesso.
7. Backend pytest exit 0; frontend verde.
