# Alerta de job quebrado — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o sistema avisar um humano quando o worker/beat para de executar tasks (o incidente de 2026-07-28) ou quando uma task individual estoura exceção.

**Architecture:** Dois sinais independentes contra um monitor externo (healthchecks.io). (1) Uma task de heartbeat agendada no beat a cada 15 min executa `SELECT 1` pelo mesmo caminho `run_async` dos jobs reais e, só se der certo, faz `POST` na URL do check — se qualquer elo (beat → redis → worker → thread → DB) quebrar, o ping não sai e o healthchecks.io alerta ao vencer o grace. (2) Um handler do sinal `task_failure` do Celery faz `POST` no `/fail` de um segundo check com o nome da task e a exceção. Um único módulo (`app/core/monitoring.py`) fala com o mundo externo, e ele engole toda exceção: monitor nunca derruba o job que monitora.

**Tech Stack:** Python 3.12, Celery 5.4, httpx ≥0.28 (já é dependência de produção em `backend/pyproject.toml:30`), pydantic-settings, pytest. Testes rodam em Docker.

**Spec:** `docs/superpowers/specs/2026-07-28-alerta-de-job-quebrado-design.md`

## Global Constraints

- **Sem tabela nova e sem dependência nova.** `httpx` já está em `backend/pyproject.toml`. Nada de migração Alembic neste trabalho.
- **Um monitor nunca pode derrubar o job que ele monitora.** Todo caminho de rede é `try/except Exception` + `logger.warning`, jamais re-raise.
- **URL não configurada = no-op silencioso.** Dev e CI não tocam a rede; o código pode ir para produção antes de a conta no healthchecks.io existir.
- **Timeout de 5s** em toda chamada externa.
- **Sem rede real nos testes** — `httpx.MockTransport` sempre.
- Os dois settings são `str | None = None` (`monitor_heartbeat_url`, `monitor_failure_url`), lidos do `.env` como `MONITOR_HEARTBEAT_URL` / `MONITOR_FAILURE_URL`.
- Segredos (as URLs reais) só em `/opt/aath/.env` no servidor, chmod 600 — **nunca** no git.
- Comando de teste do projeto: `docker compose exec api pytest -q` (ver `Makefile:62`). O código do backend está montado no container; não precisa rebuild para rodar teste.
- Estilo do repo: `from __future__ import annotations` no topo, docstring de módulo em uma linha, docstring de teste explicando **qual regressão** o teste trava (ver `backend/app/tests/test_jobs/test_run_async.py:1-8`).

---

## File Structure

| Arquivo | Papel |
|---|---|
| `backend/app/core/monitoring.py` (novo) | `ping_monitor()` — único ponto que fala com o healthchecks.io. Sem import de nada do domínio. |
| `backend/app/core/config.py` (modificar) | Os dois settings novos. |
| `backend/app/jobs/health_job.py` (novo) | Task `monitoring_heartbeat` + função `alert_task_failure` (o handler do sinal, definida aqui para ser testável sem importar o app do Celery). |
| `backend/app/jobs/celery_app.py` (modificar) | Liga o handler ao sinal `task_failure` e adiciona a entrada de 900s no `beat_schedule`. Só fiação. |
| `.env.example` (modificar) | As duas variáveis, documentadas. |
| `backend/app/tests/test_jobs/test_monitoring.py` (novo) | Testes de `ping_monitor`. |
| `backend/app/tests/test_jobs/test_health_job.py` (novo) | Testes do heartbeat e do handler. |
| `backend/app/tests/test_jobs/test_monitoring_wiring.py` (novo) | Testes da fiação no `celery_app`. |

Nada de pacote de teste novo: tudo cai em `app/tests/test_jobs/`, que já existe (`backend/app/tests/test_jobs/__init__.py`).

**Desvio consciente do spec (duas refinações, ambas aditivas):**

1. `ping_monitor()` recebe um parâmetro extra `transport` (keyword, default `None`), repassado ao `httpx.Client`. É a costura de teste que permite `httpx.MockTransport` sem monkeypatch de biblioteca. Produção nunca passa esse argumento.
2. O spec diz "handler do `task_failure` em `celery_app.py`". A **função** mora em `health_job.py` e o `connect()` fica em `celery_app.py`. Motivo: testar a função sem instanciar o app do Celery, e manter `celery_app.py` só como fiação — o mesmo padrão dos outros jobs, que se registram no fim do arquivo.

---

### Task 1: `ping_monitor` + settings + `.env.example`

**Files:**
- Create: `backend/app/core/monitoring.py`
- Modify: `backend/app/core/config.py` (bloco novo depois de "Bootstrap admin", antes dos `@computed_field`)
- Modify: `.env.example` (bloco novo no fim)
- Test: `backend/app/tests/test_jobs/test_monitoring.py`

**Interfaces:**
- Consumes: nada (primeira task).
- Produces:
  - `app.core.monitoring.ping_monitor(url: str | None, suffix: str = "", body: str | None = None, *, transport: httpx.BaseTransport | None = None) -> bool` — `True` se o POST saiu com status 2xx; `False` em qualquer outro caso (URL vazia, erro de rede, timeout, status ruim). Nunca levanta.
  - `settings.monitor_heartbeat_url: str | None`
  - `settings.monitor_failure_url: str | None`

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/app/tests/test_jobs/test_monitoring.py`:

```python
"""ping_monitor nunca pode derrubar o job que ele monitora.

Regressão que este módulo previne: em 2026-07-28 o worker ficou ~7 dias sem
executar nenhuma task e ninguém percebeu (PR #17). O ping é o sinal de vida —
mas um monitor que levanta exceção, ou que segura o worker esperando um
serviço externo, seria pior do que não ter monitor nenhum.
"""
from __future__ import annotations

import httpx

from app.core.monitoring import ping_monitor


def test_no_request_when_url_is_not_configured():
    """URL vazia => no-op silencioso. Dev, CI e prod-antes-da-conta não tocam a rede."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)

    assert ping_monitor(None, transport=transport) is False
    assert ping_monitor("", transport=transport) is False
    assert calls == []


def test_posts_to_the_configured_url():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    ok = ping_monitor(
        "https://hc-ping.example/uuid", transport=httpx.MockTransport(handler)
    )

    assert ok is True
    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert str(calls[0].url) == "https://hc-ping.example/uuid"


def test_appends_fail_suffix_without_doubling_the_slash():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    ping_monitor("https://hc-ping.example/uuid", suffix="/fail", transport=transport)
    ping_monitor("https://hc-ping.example/uuid/", suffix="/fail", transport=transport)

    assert [str(c.url) for c in calls] == [
        "https://hc-ping.example/uuid/fail",
        "https://hc-ping.example/uuid/fail",
    ]


def test_sends_the_body_when_given():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    ping_monitor(
        "https://hc-ping.example/uuid",
        body="task=garmin_sync error=boom",
        transport=httpx.MockTransport(handler),
    )

    assert calls[0].content == b"task=garmin_sync error=boom"


def test_network_error_does_not_propagate():
    """healthchecks.io fora do ar não pode quebrar o job."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns is down", request=request)

    assert (
        ping_monitor("https://hc-ping.example/uuid", transport=httpx.MockTransport(handler))
        is False
    )


def test_timeout_does_not_propagate():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    assert (
        ping_monitor("https://hc-ping.example/uuid", transport=httpx.MockTransport(handler))
        is False
    )


def test_bad_status_is_false_but_does_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert (
        ping_monitor("https://hc-ping.example/uuid", transport=httpx.MockTransport(handler))
        is False
    )
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec api pytest app/tests/test_jobs/test_monitoring.py -v`
Expected: FAIL na coleta — `ModuleNotFoundError: No module named 'app.core.monitoring'`

- [ ] **Step 3: Implementar `ping_monitor`**

Criar `backend/app/core/monitoring.py`:

```python
"""Ping de um monitor externo (healthchecks.io). Único ponto que sai para a rede.

Regra que governa este módulo: um monitor NUNCA pode derrubar o job que ele
monitora. Toda exceção é engolida e logada como warning.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0


def ping_monitor(
    url: str | None,
    suffix: str = "",
    body: str | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> bool:
    """POST no check do monitor externo. Devolve True só se o ping saiu (2xx).

    url:       URL do check. Vazia/None => no-op silencioso (retorna False).
    suffix:    "/fail" para sinalizar falha em vez de sucesso.
    body:      corpo opcional (aparece no alerta do healthchecks.io).
    transport: costura de teste (httpx.MockTransport). Produção não passa.
    """
    if not url:
        return False

    target = f"{url.rstrip('/')}{suffix}" if suffix else url
    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS, transport=transport) as client:
            response = client.post(target, content=body or b"")
        if response.is_success:
            return True
        logger.warning("monitor ping returned %s for %s", response.status_code, target)
        return False
    except Exception as exc:  # noqa: BLE001 — monitor nunca derruba o job
        logger.warning("monitor ping failed for %s: %r", target, exc)
        return False
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `docker compose exec api pytest app/tests/test_jobs/test_monitoring.py -v`
Expected: PASS (7 testes)

- [ ] **Step 5: Adicionar os settings**

Em `backend/app/core/config.py`, inserir depois do bloco "Bootstrap admin" (linhas 62-64) e antes do primeiro `@computed_field`:

```python
    # Monitoramento externo (healthchecks.io). Vazio => ping vira no-op.
    # Heartbeat: o beat pinga a cada 15 min; o check alerta se o ping sumir.
    # Failure: recebe POST em /fail quando qualquer task do Celery estoura.
    monitor_heartbeat_url: str | None = None
    monitor_failure_url: str | None = None
```

- [ ] **Step 6: Documentar no `.env.example`**

Acrescentar no fim de `.env.example`:

```bash
# --- Monitoramento externo (healthchecks.io) ---
# Vazio = desligado (o ping vira no-op; nada quebra).
# Crie 2 checks e cole as URLs de ping aqui — só no .env do servidor, nunca no git:
#   aath-heartbeat     — period 15 min, grace 20 min
#   aath-task-failure  — period bem longo; silêncio é o estado BOM neste check
MONITOR_HEARTBEAT_URL=
MONITOR_FAILURE_URL=
```

- [ ] **Step 7: Rodar a suíte inteira**

Run: `docker compose exec api pytest -q`
Expected: PASS — nenhuma regressão (settings novos têm default, ninguém quebra)

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/monitoring.py backend/app/core/config.py .env.example backend/app/tests/test_jobs/test_monitoring.py
git commit -m "feat(monitoring): ping_monitor + settings das URLs do healthchecks.io"
```

---

### Task 2: task de heartbeat e handler de falha

**Files:**
- Create: `backend/app/jobs/health_job.py`
- Test: `backend/app/tests/test_jobs/test_health_job.py`

**Interfaces:**
- Consumes: `app.core.monitoring.ping_monitor(url, suffix="", body=None) -> bool` (Task 1); `settings.monitor_heartbeat_url`, `settings.monitor_failure_url` (Task 1); `app.jobs._run.run_async(coro) -> Any` (já existe, `backend/app/jobs/_run.py:26`).
- Produces:
  - `app.jobs.health_job.monitoring_heartbeat() -> dict` — task Celery registrada com o nome `"monitoring_heartbeat"` (Task 3 referencia esse nome no `beat_schedule`). Retorna `{"pinged": bool}`. **Levanta** se o DB/thread falhar — é o que faz o `task_failure` disparar.
  - `app.jobs.health_job.alert_task_failure(sender=None, task_id=None, exception=None, **kwargs) -> None` — handler do sinal, conectado na Task 3. Nunca levanta.
  - `app.jobs.health_job._check_db()` — coroutine interna; os testes fazem monkeypatch dela.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/app/tests/test_jobs/test_health_job.py`:

```python
"""O heartbeat só pode pingar se o worker realmente conseguiu executar a task.

Regressão de 2026-07-28: o worker respondia `celery inspect ping` (o broker
estava OK) mas não conseguia executar NENHUMA task — `RuntimeError: can't start
new thread`. Um monitor que pingasse de fora teria ficado VERDE o incidente
inteiro. Por isso o ping vive dentro da task e só acontece DEPOIS de o caminho
real (run_async -> asyncio.run -> thread -> DB) ter dado certo.
"""
from __future__ import annotations

from app.core import database
from app.jobs import health_job


class _StubEngine:
    """run_async dispõe o engine global no fim; substituímos por um stub."""

    async def dispose(self) -> None:
        return None


def test_heartbeat_pings_when_the_db_answers(monkeypatch):
    monkeypatch.setattr(database, "engine", _StubEngine())

    async def fake_check_db():
        return None

    calls: list[tuple] = []
    monkeypatch.setattr(health_job, "_check_db", fake_check_db)
    monkeypatch.setattr(
        health_job,
        "ping_monitor",
        lambda url, *a, **kw: calls.append((url, a, kw)) or True,
    )
    monkeypatch.setattr(health_job.settings, "monitor_heartbeat_url", "https://hc/uuid")

    assert health_job.monitoring_heartbeat() == {"pinged": True}
    assert calls == [("https://hc/uuid", (), {})]


def test_heartbeat_does_not_ping_when_the_db_fails(monkeypatch):
    """DB fora => nenhum ping e a exceção SOBE (para o task_failure agir)."""
    monkeypatch.setattr(database, "engine", _StubEngine())

    async def fake_check_db():
        raise RuntimeError("can't start new thread")

    calls: list[str] = []
    monkeypatch.setattr(health_job, "_check_db", fake_check_db)
    monkeypatch.setattr(health_job, "ping_monitor", lambda url, *a, **kw: calls.append(url))
    monkeypatch.setattr(health_job.settings, "monitor_heartbeat_url", "https://hc/uuid")

    try:
        health_job.monitoring_heartbeat()
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("a exceção precisa subir para o task_failure disparar")
    assert calls == []


def test_alert_task_failure_pings_fail_with_task_name_and_exception(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        health_job, "ping_monitor", lambda url, *a, **kw: calls.append((url, a, kw))
    )
    monkeypatch.setattr(health_job.settings, "monitor_failure_url", "https://hc/fail-uuid")

    class _Sender:
        name = "garmin_sync"

    health_job.alert_task_failure(
        sender=_Sender(), task_id="abc-123", exception=ValueError("boom")
    )

    assert len(calls) == 1
    url, args, kwargs = calls[0]
    assert url == "https://hc/fail-uuid"
    assert kwargs["suffix"] == "/fail"
    assert "garmin_sync" in kwargs["body"]
    assert "abc-123" in kwargs["body"]
    assert "boom" in kwargs["body"]


def test_alert_task_failure_never_raises(monkeypatch):
    """Exceção dentro do handler mascararia o erro original da task."""

    def exploding_ping(*a, **kw):
        raise RuntimeError("monitor exploded")

    monkeypatch.setattr(health_job, "ping_monitor", exploding_ping)
    monkeypatch.setattr(health_job.settings, "monitor_failure_url", "https://hc/fail-uuid")

    try:
        health_job.alert_task_failure(
            sender=None, task_id=None, exception=ValueError("boom")
        )
    except Exception as exc:  # pragma: no cover
        raise AssertionError(f"o handler deixou vazar {exc!r}") from exc
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec api pytest app/tests/test_jobs/test_health_job.py -v`
Expected: FAIL na coleta — `ImportError: cannot import name 'health_job'`

- [ ] **Step 3: Implementar o job**

Criar `backend/app/jobs/health_job.py`:

```python
"""Heartbeat do worker e alerta de task falhada (monitor externo).

O ping do heartbeat só sai DEPOIS de run_async ter executado de verdade: é o
mesmo caminho (asyncio.run -> shutdown_default_executor -> thread.start()) que
estourou no incidente de 2026-07-28. Um check externo teria ficado verde.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.monitoring import ping_monitor
from app.jobs._run import run_async

logger = logging.getLogger(__name__)


async def _check_db() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))


def monitoring_heartbeat() -> dict:
    """Beat entry-point: prova que o worker executa task e pinga o monitor."""
    run_async(_check_db())  # falhou aqui => sem ping E task_failure dispara
    pinged = ping_monitor(settings.monitor_heartbeat_url)
    return {"pinged": pinged}


def alert_task_failure(sender=None, task_id=None, exception=None, **kwargs) -> None:
    """Handler do sinal task_failure do Celery. Blindado: nunca levanta.

    Uma exceção aqui mascararia o erro original da task — justamente o que se
    quer enxergar.
    """
    try:
        name = getattr(sender, "name", None) or "unknown"
        ping_monitor(
            settings.monitor_failure_url,
            suffix="/fail",
            body=f"task={name} id={task_id} error={exception!r}",
        )
    except Exception as exc:  # noqa: BLE001 — alerta nunca mascara a falha real
        logger.warning("task_failure alert failed: %r", exc)


# Registra no Celery quando o app estiver disponível (ignorado nos testes).
try:
    from app.jobs.celery_app import celery

    monitoring_heartbeat = celery.task(name="monitoring_heartbeat")(monitoring_heartbeat)  # type: ignore[assignment]
except Exception:  # noqa: BLE001 — importável sem broker (testes)
    pass
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `docker compose exec api pytest app/tests/test_jobs/test_health_job.py -v`
Expected: PASS (4 testes)

Se o `monkeypatch.setattr(health_job, "monitoring_heartbeat", ...)` da task registrada atrapalhar (o decorator do Celery embrulha a função), confirme que `monitoring_heartbeat()` chamado direto ainda executa o corpo — `celery.task` mantém a função chamável. Se o registro tiver acontecido, `health_job.monitoring_heartbeat` é a Task; chamá-la roda o corpo normalmente (eager, no processo).

- [ ] **Step 5: Commit**

```bash
git add backend/app/jobs/health_job.py backend/app/tests/test_jobs/test_health_job.py
git commit -m "feat(monitoring): task de heartbeat e handler de task_failure"
```

---

### Task 3: fiação no Celery (beat + sinal)

**Files:**
- Modify: `backend/app/jobs/celery_app.py:24-31`
- Test: `backend/app/tests/test_jobs/test_monitoring_wiring.py`

**Interfaces:**
- Consumes: `app.jobs.health_job.monitoring_heartbeat` (nome de task `"monitoring_heartbeat"`) e `app.jobs.health_job.alert_task_failure` (Task 2).
- Produces: entrada `"monitoring-heartbeat"` em `celery.conf.beat_schedule` com `schedule=900.0`; `alert_task_failure` conectado ao sinal `celery.signals.task_failure`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/app/tests/test_jobs/test_monitoring_wiring.py`:

```python
"""O alerta só existe se estiver ligado no beat e no sinal.

Sem a entrada no beat_schedule o heartbeat nunca roda; sem o connect() o
task_failure nunca alerta. Os dois são uma linha fácil de perder num rebase, e
a falha seria silenciosa — exatamente o modo de falha que este trabalho ataca.
"""
from __future__ import annotations

from celery.signals import task_failure

from app.jobs import health_job
from app.jobs.celery_app import celery


def test_heartbeat_is_scheduled_every_15_minutes():
    entry = celery.conf.beat_schedule["monitoring-heartbeat"]
    assert entry["task"] == "monitoring_heartbeat"
    assert entry["schedule"] == 900.0


def test_daily_garmin_sync_is_still_scheduled():
    """A entrada nova não pode substituir o beat_schedule existente."""
    assert celery.conf.beat_schedule["garmin-daily-sync"]["task"] == "garmin_beat_sync_all"


def test_task_failure_signal_reaches_the_alert(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        health_job, "ping_monitor", lambda url, *a, **kw: calls.append((url, kw))
    )
    monkeypatch.setattr(health_job.settings, "monitor_failure_url", "https://hc/fail-uuid")

    class _Sender:
        name = "garmin_sync"

    task_failure.send(sender=_Sender(), task_id="abc-123", exception=ValueError("boom"))

    assert len(calls) == 1
    assert calls[0][0] == "https://hc/fail-uuid"
    assert calls[0][1]["suffix"] == "/fail"
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec api pytest app/tests/test_jobs/test_monitoring_wiring.py -v`
Expected: FAIL — `KeyError: 'monitoring-heartbeat'` no primeiro teste e `assert 0 == 1` no terceiro (nenhum receiver conectado)

- [ ] **Step 3: Ligar o beat e o sinal**

Em `backend/app/jobs/celery_app.py`, substituir as linhas 24-31 por:

```python
from app.jobs import import_job, metrics_job, profile_job, garmin_job, health_job  # noqa: E402,F401

# Alerta imediato quando QUALQUER task estoura (ver app/jobs/health_job.py).
from celery.signals import task_failure  # noqa: E402

task_failure.connect(health_job.alert_task_failure, weak=False)

celery.conf.beat_schedule = {
    "garmin-daily-sync": {
        "task": "garmin_beat_sync_all",
        "schedule": 24 * 60 * 60.0,  # daily
    },
    "monitoring-heartbeat": {
        "task": "monitoring_heartbeat",
        "schedule": 900.0,  # 15 min — grace de 20 min no healthchecks.io
    },
}
```

`weak=False` é obrigatório: com referência fraca o receiver pode ser coletado e o alerta some sem aviso.

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `docker compose exec api pytest app/tests/test_jobs/test_monitoring_wiring.py -v`
Expected: PASS (3 testes)

- [ ] **Step 5: Rodar a suíte inteira**

Run: `docker compose exec api pytest -q`
Expected: PASS, sem regressão. Atenção especial: nenhum teste existente pode passar a fazer chamada de rede (as URLs são `None` por padrão, então o ping é no-op).

- [ ] **Step 6: Commit**

```bash
git add backend/app/jobs/celery_app.py backend/app/tests/test_jobs/test_monitoring_wiring.py
git commit -m "feat(monitoring): agenda o heartbeat no beat e liga o sinal task_failure"
```

---

### Task 4: nota de operação (runbook)

**Files:**
- Create: `docs/ops/alerta-de-job-quebrado.md`

Sem teste automatizado: é documentação do que o operador faz fora do código. É a única coisa que não está no repositório depois das Tasks 1-3.

- [ ] **Step 1: Escrever o runbook**

Criar `docs/ops/alerta-de-job-quebrado.md`:

```markdown
# Alerta de job quebrado — operação

Dois checks no healthchecks.io (free tier). Sem eles configurados o código roda
igual, só não alerta.

## Configurar (uma vez)

1. Criar conta em https://healthchecks.io
2. Criar `aath-heartbeat` — **period 15 min, grace 20 min**
3. Criar `aath-task-failure` — **period bem longo (ex.: 365 dias)**. Aqui o
   silêncio é o estado BOM; com period curto o check alertaria sozinho.
4. Copiar as duas URLs de ping para `/opt/aath/.env` (chmod 600, nunca no git):

   ```
   MONITOR_HEARTBEAT_URL=https://hc-ping.com/<uuid-do-heartbeat>
   MONITOR_FAILURE_URL=https://hc-ping.com/<uuid-do-failure>
   ```

5. Configurar o canal de notificação (email) nos dois checks.

## Deploy

O código mudou, então rebuild da imagem do backend e recriar `worker` **e**
`beat` — o beat precisa reiniciar para carregar o `beat_schedule` novo. O `api`
roda a mesma imagem e não usa nada disto; recriar é opcional, só para manter os
três na mesma build. Os dois containers já leem `env_file: .env`, então não há
mudança de compose.

## O que cada alerta significa

| Alerta | Significado | Primeiro passo |
|---|---|---|
| `aath-heartbeat` vermelho | beat, redis, worker ou postgres fora — ou o worker vivo sem conseguir executar task (o caso de 2026-07-28) | `docker compose ps` e checar `State.Health`; `docker stats --no-stream --format "{{.Name}}\|{{.PIDs}}"` para ver vazamento de processo |
| `aath-task-failure` disparou | a infra está de pé, uma task individual estourou. O corpo do alerta traz nome da task, id e a exceção | `docker logs aath_worker` filtrando pelo id da task |

Se a própria task de heartbeat falhar, chegam **dois** alertas (o `/fail`
imediato e depois a janela vencida). É redundância de propósito, não ruído.

**Antes de recriar um container em incidente:** `docker logs <container> >
/tmp/incidente.log`. Recriar descarta os logs antigos — foi o que se perdeu no
incidente de 2026-07-28.
```

- [ ] **Step 2: Commit**

```bash
git add docs/ops/alerta-de-job-quebrado.md
git commit -m "docs(ops): runbook do alerta de job quebrado"
```

---

## Verificação final (com evidência, não com fé)

Depois das quatro tasks, antes de considerar pronto:

- [ ] `docker compose exec api pytest -q` — suíte inteira verde, colar a saída
- [ ] **Sem URL configurada nada quebra:** `docker compose exec worker python -c "from app.jobs.health_job import monitoring_heartbeat; print(monitoring_heartbeat())"` → imprime `{'pinged': False}` sem exceção
- [ ] **Heartbeat real (depois de as URLs entrarem no `.env` de produção):** disparar a task manualmente e ver o check `aath-heartbeat` virar verde no painel do healthchecks.io
- [ ] **Alerta de falha real:** forçar uma task a estourar e confirmar que o email chega com nome da task e a exceção no corpo
- [ ] **Beat carregou a agenda:** `docker logs aath_beat` mostra `monitoring-heartbeat` na lista de entradas ao subir

A verificação de produção depende das URLs do healthchecks.io, que são
pendência do operador. As Tasks 1-4 podem ir para a main e para o servidor
antes disso — sem URL o ping é no-op e nada quebra.
