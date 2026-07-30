# Integração Whoop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trazer HRV, FC de repouso, score de recuperação, horas e performance de sono da Whoop para `recovery_metrics`, com a Whoop tendo precedência sobre o Garmin.

**Architecture:** Reusa o molde da conexão Garmin — uma linha por atleta com token criptografado, job no beat, card na tela de importação. A Whoop é mais simples: API oficial OAuth2, sem senha do usuário passando pelo nosso lado, sem MFA. O ponto novo é um módulo de merge compartilhado que aplica a precedência entre fontes e, de quebra, corrige o bug em que o sync do Garmin escreve vazio por cima de dado bom.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Celery 5.4, httpx ≥0.28 (já é dependência), cryptography/Fernet (já é dependência), Next.js 15 no web. Testes em Docker, na VM.

**Spec:** `docs/superpowers/specs/2026-07-29-integracao-whoop-design.md`

## Global Constraints

- **Sem dependência nova.** `httpx` e `cryptography` já estão em `backend/pyproject.toml`.
- **Uma migração Alembic apenas** — tabela `whoop_connections`. `recovery_metrics` **não muda**.
- **Não tocar em `garmin_token_key` nem no `.env` de produção.** A interface pública do token store do Garmin (`is_enabled`/`encrypt`/`decrypt`) permanece idêntica.
- **Feature desligada por padrão:** `whoop_client_id`, `whoop_client_secret`, `whoop_token_key` vazios ⇒ rotas em 503 e card ausente.
- **Sem rede real nos testes.** `httpx.MockTransport` para o client; client falso para o sync.
- **Base da API:** `https://api.prod.whoop.com/developer/v2/`. OAuth: auth em `https://api.prod.whoop.com/oauth/oauth2/auth`, token em `https://api.prod.whoop.com/oauth/oauth2/token`.
- **Escopos:** `read:recovery read:sleep offline`.
- **Paginação:** `limit` (máximo 25), `start`, `end` (ISO 8601), `nextToken`; envelope `{"records": [...], "next_token": "..."}`.
- **Dois filtros obrigatórios:** descartar `nap == true`; usar só `score_state == "SCORED"`.
- **Data do registro:** `metric_date` = data local do **fim do sono**, via o `timezone_offset` do próprio objeto de sono (ex.: `"-03:00"`).
- **Precedência:** `whoop` sobrescreve; `garmin` nunca escreve vazio e nunca sobrescreve campo preenchido em dia que a Whoop alimentou.
- **Janela do sync diário:** últimos 3 dias. **Backfill inicial:** 180 dias.
- **Cron do beat:** 08:00 UTC (05:00 no Brasil).
- **Validade do `state` do OAuth:** 10 minutos.
- Estilo do repo: `from __future__ import annotations` no topo, docstring de módulo, docstrings de teste explicando qual regressão o teste trava.
- Suíte do backend na linha de base: **522 testes**, 1 warning conhecido (`passlib`/`crypt`, pré-existente).

## Como rodar os testes do backend

O backend **não roda nesta máquina** — o Docker local está desligado de propósito
(decisão do usuário, 2026-07-29). Os testes rodam na VM da Contabo, num container
efêmero isolado da produção. Se o wrapper abaixo não existir, recrie-o:

```bash
#!/usr/bin/env bash
# Sincroniza backend/ (inclusive alterações não commitadas) para /opt/aath-test
# na VM e roda pytest num container efêmero. NUNCA toca /opt/aath (produção).
set -euo pipefail
REPO="/c/projetos/treinador-ciclismo"
VM="root@62.171.128.103"
SSH="ssh -i $HOME/.ssh/id_ed25519_aath_vps -o BatchMode=yes -o ConnectTimeout=20"
cd "$REPO"
tar -cz -C backend --exclude=__pycache__ --exclude=.pytest_cache --exclude=.ruff_cache \
    --exclude='*.egg-info' --exclude='*.pyc' . \
  | $SSH "$VM" "rm -rf /opt/aath-test/backend && mkdir -p /opt/aath-test/backend && tar -xz -C /opt/aath-test/backend"
$SSH "$VM" "docker run --rm -v /opt/aath-test/backend:/app -w /app aath-test:latest pytest $*"
```

Salve como `vm-test.sh` fora do repositório (ele é ferramenta de sessão, não
código do projeto) e use `bash vm-test.sh <args>`. A imagem `aath-test:latest`
já existe na VM (`aath-api` + `pytest`, `pytest-asyncio`, `pytest-cov`,
`aiosqlite`); se faltar, reconstrua com um Dockerfile de duas linhas partindo de
`aath-api:latest`. A suíte inteira leva ~3,5 min — use timeout de 420000 ms.

Os testes do **web** rodam no host normalmente: `cd web && npx vitest run`.

---

## File Structure

| Arquivo | Papel |
|---|---|
| `backend/app/core/token_crypto.py` (novo) | Lógica Fernet compartilhada, chave passada por parâmetro. |
| `backend/app/services/garmin/token_store.py` (modificar) | Vira invólucro fino sobre `token_crypto`. Interface pública intacta. |
| `backend/app/services/whoop/token_store.py` (novo) | Invólucro com `whoop_token_key`. |
| `backend/app/core/config.py` (modificar) | `whoop_client_id`, `whoop_client_secret`, `whoop_token_key`. |
| `backend/app/services/recovery/merge.py` (novo) | `RecoverySnapshot` + `merge_into()`. O coração da precedência. |
| `backend/app/services/garmin/sync_service.py` (modificar) | Passa a gravar via `merge_into` (corrige o bug do vazio). |
| `backend/app/models/enums.py` (modificar) | `WhoopConnectionStatus`. |
| `backend/app/models/whoop.py` (novo) | `WhoopConnection`. |
| `backend/alembic/versions/*_whoop_connections.py` (novo) | Migração da tabela. |
| `backend/app/services/whoop/types.py` (novo) | `WhoopDay` (snapshot + data), erros do domínio. |
| `backend/app/services/whoop/client.py` (novo) | Único ponto que fala HTTP com a Whoop. |
| `backend/app/services/whoop/fake_client.py` (novo) | Client determinístico para teste offline. |
| `backend/app/services/whoop/sync_service.py` (novo) | Orquestra o pull e a gravação. |
| `backend/app/services/whoop/oauth_state.py` (novo) | Assina e valida o `state`. |
| `backend/app/jobs/whoop_job.py` (novo) | Backfill, sync de um atleta, entrada do beat. |
| `backend/app/jobs/celery_app.py` (modificar) | Cron 08:00 UTC no `beat_schedule`. |
| `backend/app/schemas/whoop.py` (novo) | `WhoopStatusRead`, `WhoopCallbackRequest`. |
| `backend/app/api/routes/whoop.py` (novo) | authorize, callback, status, disconnect, sync. |
| `backend/app/api/routes/__init__.py` ou `main.py` (modificar) | Registrar o router. |
| `web/lib/types.ts` (modificar) | Tipo `WhoopStatus`. |
| `web/lib/hooks.ts` (modificar) | `useWhoopStatus()`, no molde de `useGarminStatus`. |
| `web/components/importar/WhoopCard.tsx` (novo) | Card de conexão. |
| `web/app/api/whoop/callback/route.ts` (novo) | Recebe o redirect e repassa ao backend. |
| `.env.example` (modificar) | As três variáveis, documentadas. |
| `docs/ops/integracao-whoop.md` (novo) | Runbook do operador. |

Testes espelham a estrutura em `backend/app/tests/test_whoop/` e `backend/app/tests/test_recovery/`.

---

### Task 1: `token_crypto` compartilhado + settings da Whoop

**Files:**
- Create: `backend/app/core/token_crypto.py`
- Modify: `backend/app/services/garmin/token_store.py`
- Create: `backend/app/services/whoop/token_store.py`, `backend/app/services/whoop/__init__.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Test: `backend/app/tests/test_whoop/test_token_store.py`, `backend/app/tests/test_whoop/__init__.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `app.core.token_crypto.encrypt(data: dict, key: str, name: str) -> str`
  - `app.core.token_crypto.decrypt(blob: str, key: str, name: str) -> dict`
  - `app.core.token_crypto.TokenCryptoError`
  - `app.services.whoop.token_store.is_enabled() -> bool`, `encrypt(dict) -> str`, `decrypt(str) -> dict`, `WhoopCryptoError`
  - `settings.whoop_client_id`, `settings.whoop_client_secret`, `settings.whoop_token_key` (todos `str`, default `""`)

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/app/tests/test_whoop/__init__.py` (vazio) e `backend/app/tests/test_whoop/test_token_store.py`:

```python
"""O token da Whoop nunca fica em claro no banco.

Regressão que este módulo previne: um refresh token vazado dá acesso de leitura
contínuo aos dados de saúde do atleta. Ele só entra na coluna criptografado, e
uma chave ausente falha alto em vez de gravar texto puro.
"""
from __future__ import annotations

import pytest

from app.core import token_crypto
from app.services.whoop import token_store


def test_round_trip_preserves_the_token(monkeypatch):
    monkeypatch.setattr(token_store.settings, "whoop_token_key", _KEY)
    original = {"access_token": "at-123", "refresh_token": "rt-456", "expires_at": 1785000000}

    blob = token_store.encrypt(original)

    assert "at-123" not in blob  # não vaza em claro
    assert token_store.decrypt(blob) == original


def test_missing_key_raises_naming_the_setting(monkeypatch):
    monkeypatch.setattr(token_store.settings, "whoop_token_key", "")

    with pytest.raises(token_store.WhoopCryptoError, match="whoop_token_key"):
        token_store.encrypt({"access_token": "x"})


def test_is_enabled_follows_the_key(monkeypatch):
    monkeypatch.setattr(token_store.settings, "whoop_token_key", "")
    assert token_store.is_enabled() is False
    monkeypatch.setattr(token_store.settings, "whoop_token_key", _KEY)
    assert token_store.is_enabled() is True


def test_garbage_blob_raises_instead_of_returning_junk(monkeypatch):
    monkeypatch.setattr(token_store.settings, "whoop_token_key", _KEY)

    with pytest.raises(token_store.WhoopCryptoError):
        token_store.decrypt("nao-e-um-token-fernet")


def test_shared_layer_keeps_keys_independent():
    """Chave da Whoop não decifra blob do Garmin — o vazamento de uma não expõe a outra."""
    blob = token_crypto.encrypt({"a": 1}, _KEY, "k1")

    with pytest.raises(token_crypto.TokenCryptoError):
        token_crypto.decrypt(blob, _OTHER_KEY, "k2")


_KEY = "dGVzdGUtZmVybmV0LWtleS0zMi1ieXRlcy1iYXNlNjQtb2s="
_OTHER_KEY = "b3V0cmEtY2hhdmUtZmVybmV0LTMyLWJ5dGVzLWJhc2U2NA=="
```

**Atenção:** `_KEY` e `_OTHER_KEY` precisam ser chaves Fernet válidas (32 bytes url-safe base64). Gere as duas com `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` e substitua os literais acima — os valores mostrados são ilustrativos e **vão falhar** na validação do Fernet.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_whoop/test_token_store.py -v`
Expected: FAIL na coleta — `ModuleNotFoundError: No module named 'app.core.token_crypto'`

- [ ] **Step 3: Criar a camada compartilhada**

`backend/app/core/token_crypto.py`:

```python
"""Criptografia Fernet de material secreto em repouso, com chave por integração.

Único módulo que constrói um Fernet. Cada integração passa a própria chave, para
que o vazamento de uma não exponha as outras. O parâmetro ``name`` existe só para
a mensagem de erro apontar qual setting está faltando.
"""
from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken


class TokenCryptoError(RuntimeError):
    """Criptografia/descriptografia falhou, ou a chave está ausente/inválida."""


def _fernet(key: str, name: str) -> Fernet:
    if not key:
        raise TokenCryptoError(f"{name} is not configured")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise TokenCryptoError(f"invalid {name}: {exc}") from exc


def encrypt(data: dict, key: str, name: str) -> str:
    return _fernet(key, name).encrypt(json.dumps(data).encode()).decode()


def decrypt(blob: str, key: str, name: str) -> dict:
    f = _fernet(key, name)
    try:
        return json.loads(f.decrypt(blob.encode()).decode())
    except (InvalidToken, ValueError) as exc:
        raise TokenCryptoError(f"could not decrypt token: {exc}") from exc
```

- [ ] **Step 4: Criar o token store da Whoop**

`backend/app/services/whoop/__init__.py` (vazio) e `backend/app/services/whoop/token_store.py`:

```python
"""Fronteira de criptografia do token OAuth da Whoop.

Único módulo que toca o segredo da Whoop em repouso. Access token e refresh token
passam por aqui sempre cifrados com ``settings.whoop_token_key``.
"""
from __future__ import annotations

from app.core import token_crypto
from app.core.config import settings

_KEY_NAME = "whoop_token_key"


class WhoopCryptoError(RuntimeError):
    """Criptografia falhou ou a chave está ausente."""


def is_enabled() -> bool:
    return bool(settings.whoop_token_key)


def encrypt(data: dict) -> str:
    try:
        return token_crypto.encrypt(data, settings.whoop_token_key, _KEY_NAME)
    except token_crypto.TokenCryptoError as exc:
        raise WhoopCryptoError(str(exc)) from exc


def decrypt(blob: str) -> dict:
    try:
        return token_crypto.decrypt(blob, settings.whoop_token_key, _KEY_NAME)
    except token_crypto.TokenCryptoError as exc:
        raise WhoopCryptoError(str(exc)) from exc
```

- [ ] **Step 5: Converter o store do Garmin em invólucro**

Substituir o corpo de `backend/app/services/garmin/token_store.py` mantendo a docstring e a interface pública:

```python
"""Fronteira de criptografia do token Garmin + client_state do MFA em repouso.

A senha do atleta nunca é guardada; só o token_dict do garth e o client_state de
MFA em trânsito passam por aqui, sempre cifrados com ``settings.garmin_token_key``.
A criptografia em si vive em ``app.core.token_crypto`` — compartilhada com a Whoop
para não haver duas implementações de Fernet no projeto.
"""
from __future__ import annotations

from app.core import token_crypto
from app.core.config import settings

_KEY_NAME = "garmin_token_key"


class GarminCryptoError(RuntimeError):
    """Raised when encryption/decryption fails or the key is missing."""


def is_enabled() -> bool:
    return bool(settings.garmin_token_key)


def encrypt(data: dict) -> str:
    try:
        return token_crypto.encrypt(data, settings.garmin_token_key, _KEY_NAME)
    except token_crypto.TokenCryptoError as exc:
        raise GarminCryptoError(str(exc)) from exc


def decrypt(blob: str) -> dict:
    try:
        return token_crypto.decrypt(blob, settings.garmin_token_key, _KEY_NAME)
    except token_crypto.TokenCryptoError as exc:
        raise GarminCryptoError(str(exc)) from exc
```

- [ ] **Step 5b: Rodar os testes EXISTENTES do Garmin**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_garmin/test_token_store.py -v`
Expected: PASS sem alteração no arquivo de teste. Se falhar por mensagem de erro, o `_KEY_NAME` está errado — as mensagens preservam `garmin_token_key`.

- [ ] **Step 6: Adicionar os settings**

Em `backend/app/core/config.py`, depois do bloco do `google_client_id`:

```python
    # Whoop (API oficial v2, OAuth2). Vazio => integração desligada (rotas 503).
    # whoop_token_key: chave Fernet para o token em repouso. Gere com:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    whoop_client_id: str = ""
    whoop_client_secret: str = ""
    whoop_token_key: str = ""
```

- [ ] **Step 7: Documentar no `.env.example`**

Acrescentar no fim:

```bash
# --- Whoop (HRV, sono, recuperação — API oficial v2) ---
# Vazio = integração desligada (rotas em 503, card não aparece).
# Crie o app em developer.whoop.com (imediato, limite de 10 membros sem aprovação)
# e registre o Redirect URI: https://<SEU_DOMINIO>/api/whoop/callback
WHOOP_CLIENT_ID=
WHOOP_CLIENT_SECRET=
# Fernet para o token em repouso:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
WHOOP_TOKEN_KEY=
```

- [ ] **Step 8: Rodar a suíte inteira**

Run: `bash <scratchpad>/vm-test.sh`
Expected: 522 + 5 novos = **527 passed**, 1 warning conhecido (passlib). Nenhum teste do Garmin quebrado.

- [ ] **Step 9: Commit**

```bash
git add backend/app/core/token_crypto.py backend/app/services/whoop backend/app/services/garmin/token_store.py backend/app/core/config.py .env.example backend/app/tests/test_whoop
git commit -m "refactor(crypto): extrai token_crypto compartilhado e adiciona token store da Whoop"
```

---

### Task 2: merge de fontes de recuperação (corrige o bug do Garmin)

**Files:**
- Create: `backend/app/services/recovery/__init__.py`, `backend/app/services/recovery/merge.py`
- Modify: `backend/app/services/garmin/sync_service.py:98-110`
- Test: `backend/app/tests/test_recovery/__init__.py`, `backend/app/tests/test_recovery/test_merge.py`

**Interfaces:**
- Consumes: `app.models.metrics.RecoveryMetric` (já existe).
- Produces:
  - `app.services.recovery.merge.RecoverySnapshot` — dataclass congelada com `hrv_ms: float | None`, `resting_hr: int | None`, `sleep_hours: float | None`, `sleep_score: float | None`, `recovery_score: float | None`, todos default `None`.
  - `app.services.recovery.merge.merge_into(row: RecoveryMetric, snap: RecoverySnapshot, source: str) -> bool` — devolve `True` se escreveu algo.
  - `app.services.recovery.merge.PRIORITY_SOURCES: frozenset[str]` = `frozenset({"whoop"})`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/app/tests/test_recovery/__init__.py` (vazio) e `backend/app/tests/test_recovery/test_merge.py`:

```python
"""Duas fontes, uma linha por dia — quem ganha e quem nunca apaga.

Regressão histórica (2026-07-29): o sync do Garmin fazia
``existing.hrv_ms = snap.hrv_ms`` sem checar, então um dia em que o atleta dormiu
sem o relógio gravava None por cima de um HRV bom. Com a Whoop na jogada isso
passaria a apagar o dado da pulseira todo dia.
"""
from __future__ import annotations

from app.models.metrics import RecoveryMetric
from app.services.recovery.merge import RecoverySnapshot, merge_into


def _row(**kw) -> RecoveryMetric:
    return RecoveryMetric(metric_date=None, **kw)


def test_whoop_fills_an_empty_day():
    row = _row()

    assert merge_into(row, RecoverySnapshot(hrv_ms=61.5, resting_hr=48), "whoop") is True
    assert row.hrv_ms == 61.5
    assert row.resting_hr == 48
    assert row.source == "whoop"


def test_whoop_overwrites_garmin_on_the_same_day():
    """Precedência: a pulseira 24h vence o relógio que depende de dormir com ele."""
    row = _row(hrv_ms=40.0, source="garmin")

    merge_into(row, RecoverySnapshot(hrv_ms=61.5), "whoop")

    assert row.hrv_ms == 61.5
    assert row.source == "garmin+whoop"


def test_garmin_does_not_overwrite_a_whoop_day():
    row = _row(hrv_ms=61.5, source="whoop")

    assert merge_into(row, RecoverySnapshot(hrv_ms=40.0), "garmin") is False
    assert row.hrv_ms == 61.5
    assert row.source == "whoop"


def test_garmin_fills_a_field_the_whoop_left_empty():
    """Precedência é por campo na leitura: o que a Whoop não trouxe, o Garmin preenche."""
    row = _row(hrv_ms=61.5, source="whoop")

    assert merge_into(row, RecoverySnapshot(sleep_hours=7.2), "garmin") is True
    assert row.sleep_hours == 7.2
    assert row.hrv_ms == 61.5
    assert row.source == "whoop+garmin"


def test_garmin_still_refreshes_its_own_data_on_a_garmin_only_day():
    row = _row(hrv_ms=40.0, source="garmin")

    merge_into(row, RecoverySnapshot(hrv_ms=42.0), "garmin")

    assert row.hrv_ms == 42.0


def test_empty_value_never_erases_an_existing_one():
    """O bug de 2026-07-29, travado: None não é dado, é ausência de dado."""
    row = _row(hrv_ms=61.5, sleep_hours=7.2, source="whoop")

    assert merge_into(row, RecoverySnapshot(), "garmin") is False
    assert row.hrv_ms == 61.5
    assert row.sleep_hours == 7.2

    assert merge_into(row, RecoverySnapshot(), "whoop") is False
    assert row.hrv_ms == 61.5


def test_source_does_not_duplicate_on_repeated_sync():
    row = _row()
    merge_into(row, RecoverySnapshot(hrv_ms=61.5), "whoop")
    merge_into(row, RecoverySnapshot(hrv_ms=62.0), "whoop")

    assert row.source == "whoop"
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_recovery/test_merge.py -v`
Expected: FAIL na coleta — `ModuleNotFoundError: No module named 'app.services.recovery'`

- [ ] **Step 3: Implementar o merge**

`backend/app/services/recovery/__init__.py` (vazio) e `backend/app/services/recovery/merge.py`:

```python
"""Merge de métricas de recuperação de fontes diferentes numa linha por dia.

``recovery_metrics`` tem uma linha por atleta por dia, então duas pulseiras
disputam as mesmas colunas. Duas regras resolvem:

1. **Vazio nunca apaga.** Um None na resposta da fonte significa "não medi",
   não "o valor é nulo". Antes disso ser explícito, o sync do Garmin apagava HRV
   bom nos dias em que o atleta dormia sem o relógio.
2. **A Whoop tem precedência.** É pulseira usada 24h, feita para medir sono e HRV
   noturno. O Garmin atualiza o que ele mesmo escreveu, mas não encosta em campo
   preenchido de um dia que a Whoop alimentou.

A procedência é por LINHA, não por campo (``source`` acumula os contribuintes do
dia). A consequência aceita está no spec de 2026-07-29.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

from app.models.metrics import RecoveryMetric

PRIORITY_SOURCES: frozenset[str] = frozenset({"whoop"})


@dataclass(frozen=True)
class RecoverySnapshot:
    """Um dia de recuperação, normalizado, independente da fonte."""

    hrv_ms: float | None = None
    resting_hr: int | None = None
    sleep_hours: float | None = None
    sleep_score: float | None = None
    recovery_score: float | None = None


def _row_has_priority_source(source: str | None) -> bool:
    if not source:
        return False
    return any(part in PRIORITY_SOURCES for part in source.split("+"))


def _append_source(current: str | None, incoming: str) -> str:
    parts = [p for p in (current or "").split("+") if p]
    if incoming not in parts:
        parts.append(incoming)
    return "+".join(parts)


def merge_into(row: RecoveryMetric, snap: RecoverySnapshot, source: str) -> bool:
    """Aplica ``snap`` em ``row`` segundo a precedência de ``source``.

    Devolve True se algum campo foi escrito.
    """
    protected = source not in PRIORITY_SOURCES and _row_has_priority_source(row.source)
    changed = False
    for f in fields(snap):
        new = getattr(snap, f.name)
        if new is None:
            continue  # ausência de medida nunca sobrescreve medida
        if protected and getattr(row, f.name) is not None:
            continue  # dia da Whoop: fonte sem precedência só preenche lacuna
        setattr(row, f.name, new)
        changed = True
    if changed:
        row.source = _append_source(row.source, source)
    return changed
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_recovery/test_merge.py -v`
Expected: PASS (7 testes)

- [ ] **Step 5: Fazer o sync do Garmin usar o merge**

Em `backend/app/services/garmin/sync_service.py`, trocar o bloco que hoje atribui campo por campo (linhas ~98-110) por:

```python
        while day <= today:
            snap = client.get_wellness(day)
            incoming = RecoverySnapshot(
                hrv_ms=snap.hrv_ms,
                resting_hr=snap.resting_hr,
                sleep_hours=snap.sleep_hours,
                sleep_score=snap.sleep_score,
                recovery_score=snap.body_battery,
            )
            if any(getattr(incoming, f.name) is not None for f in fields(incoming)):
                existing = await rec_repo.get_for_date(day, athlete_id)
                if existing is None:
                    existing = RecoveryMetric(athlete_id=athlete_id, metric_date=day)
                    await rec_repo.add(existing)
                if merge_into(existing, incoming, "garmin"):
                    wellness_days += 1
            day += timedelta(days=1)
```

Acrescentar os imports no topo do arquivo:

```python
from dataclasses import fields

from app.services.recovery.merge import RecoverySnapshot, merge_into
```

- [ ] **Step 6: Rodar os testes existentes do Garmin**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_garmin -v`
Expected: PASS. Atenção: se algum teste afirmava que o Garmin sobrescreve com `None`, ele estava codificando o bug — nesse caso corrija o **teste** e explique na mensagem de commit, não o merge.

- [ ] **Step 7: Rodar a suíte inteira**

Run: `bash <scratchpad>/vm-test.sh`
Expected: **534 passed** (527 + 7), 1 warning conhecido.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/recovery backend/app/services/garmin/sync_service.py backend/app/tests/test_recovery
git commit -m "fix(recovery): merge com precedencia entre fontes; Garmin para de apagar dado com vazio"
```

---

### Task 3: modelo e migração de `whoop_connections`

**Files:**
- Modify: `backend/app/models/enums.py`
- Create: `backend/app/models/whoop.py`
- Modify: `backend/app/models/__init__.py` (importar o novo modelo, seguindo o padrão dos demais)
- Create: `backend/alembic/versions/<rev>_whoop_connections.py`
- Test: `backend/app/tests/test_whoop/test_model.py`

**Interfaces:**
- Consumes: `app.models.base.Base`, `TenantMixin` (já existem).
- Produces:
  - `app.models.enums.WhoopConnectionStatus` — `CONNECTED`, `NEEDS_REAUTH`, `DISCONNECTED` (**sem** `AWAITING_MFA`: a Whoop não tem esse passo).
  - `app.models.whoop.WhoopConnection` — colunas: `status`, `encrypted_token`, `last_sync_at`, `last_error`, `connected_at`, `backfilled_at`. Unique em `athlete_id`.

- [ ] **Step 1: Escrever o teste que falha**

`backend/app/tests/test_whoop/test_model.py`:

```python
"""A conexão Whoop é uma por atleta, e nunca guarda credencial em claro.

O unique em athlete_id é o que impede duas conexões concorrentes para o mesmo
atleta — cenário em que um refresh invalidaria o token do outro em silêncio.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.enums import WhoopConnectionStatus
from app.models.whoop import WhoopConnection


def test_status_has_no_mfa_state():
    """A Whoop é OAuth2 puro — um estado de MFA aqui seria copiar o Garmin sem motivo."""
    assert {s.value for s in WhoopConnectionStatus} == {
        "CONNECTED", "NEEDS_REAUTH", "DISCONNECTED",
    }


async def test_one_connection_per_athlete(session, two_athletes):
    a, _ = two_athletes
    session.add(WhoopConnection(athlete_id=a.id, tenant_id=a.tenant_id))
    await session.flush()

    session.add(WhoopConnection(athlete_id=a.id, tenant_id=a.tenant_id))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_defaults_to_disconnected(session, two_athletes):
    a, _ = two_athletes
    conn = WhoopConnection(athlete_id=a.id, tenant_id=a.tenant_id)
    session.add(conn)
    await session.flush()

    assert conn.status is WhoopConnectionStatus.DISCONNECTED
    assert conn.encrypted_token is None
    assert conn.backfilled_at is None
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_whoop/test_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'WhoopConnectionStatus'`

- [ ] **Step 3: Adicionar o enum**

Em `backend/app/models/enums.py`, depois de `GarminConnectionStatus`:

```python
class WhoopConnectionStatus(str, enum.Enum):
    CONNECTED = "CONNECTED"
    NEEDS_REAUTH = "NEEDS_REAUTH"
    DISCONNECTED = "DISCONNECTED"
```

- [ ] **Step 4: Criar o modelo**

`backend/app/models/whoop.py`:

```python
"""Vínculo com a Whoop: uma linha por atleta. Guarda o token OAuth cifrado
(nunca credencial do atleta — a Whoop é OAuth2, a senha nunca passa por nós) e
o ciclo de vida da conexão."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin
from app.models.enums import WhoopConnectionStatus


class WhoopConnection(Base, TenantMixin):
    __tablename__ = "whoop_connections"
    __table_args__ = (UniqueConstraint("athlete_id", name="uq_whoop_conn_athlete"),)

    status: Mapped[WhoopConnectionStatus] = mapped_column(
        Enum(WhoopConnectionStatus, native_enum=False, length=32),
        default=WhoopConnectionStatus.DISCONNECTED,
        nullable=False,
    )
    encrypted_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Marca que o backfill de 180 dias já rodou — evita repetir a carga inicial
    # a cada reconexão.
    backfilled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

Registrar em `backend/app/models/__init__.py` no mesmo estilo dos demais modelos (import para o `Base.metadata` enxergar a tabela).

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_whoop/test_model.py -v`
Expected: PASS (3 testes)

- [ ] **Step 6: Gerar a migração**

Run: `ssh -i ~/.ssh/id_ed25519_aath_vps root@62.171.128.103 "cd /opt/aath && docker compose -f docker-compose.prod.yml exec -T api alembic revision --autogenerate -m 'whoop_connections'"`

**Não confie no autogenerate cegamente:** abra o arquivo gerado e confirme que ele cria `whoop_connections` com as seis colunas, o unique `uq_whoop_conn_athlete`, e as colunas do `TenantMixin` (`athlete_id`, `tenant_id`, `id`, `created_at`, `updated_at`, `deleted_at`) — e que **não** altera nenhuma outra tabela. Se aparecer qualquer `alter_table` em tabela existente, apague essa linha: é ruído de drift do autogenerate, não intenção deste trabalho.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/whoop.py backend/app/models/enums.py backend/app/models/__init__.py backend/alembic/versions backend/app/tests/test_whoop/test_model.py
git commit -m "feat(whoop): modelo e migracao de whoop_connections"
```

---

### Task 4: client HTTP da Whoop

**Files:**
- Create: `backend/app/services/whoop/types.py`, `backend/app/services/whoop/client.py`
- Test: `backend/app/tests/test_whoop/test_client.py`

**Interfaces:**
- Consumes: `settings.whoop_client_id`, `settings.whoop_client_secret` (Task 1).
- Produces:
  - `app.services.whoop.types.WhoopAuthError`, `WhoopSyncError`, `WhoopRateLimited` (com atributo `retry_after_s: int | None`)
  - `app.services.whoop.types.WhoopDay` — dataclass congelada: `metric_date: date`, `snapshot: RecoverySnapshot`
  - `app.services.whoop.client.authorize_url(state: str, redirect_uri: str) -> str`
  - `app.services.whoop.client.WhoopClient(token: dict, *, transport=None)` com:
    - `exchange_code(code, redirect_uri) -> dict` (classmethod)
    - `refresh() -> dict`
    - `fetch_days(start: date, end: date) -> list[WhoopDay]`
    - `token: dict` (propriedade com o token corrente, já renovado se preciso)

- [ ] **Step 1: Escrever os testes que falham**

`backend/app/tests/test_whoop/test_client.py`:

```python
"""O client traduz a semântica da Whoop para a nossa, e nunca vaza exceção crua.

Três regras da API que, ignoradas, gravariam lixo como se fosse medição:
- recovery não tem data: ela aponta para o sono por sleep_id
- nap=true é cochilo, não a noite
- score_state != SCORED significa que o score não existe ou está incompleto
"""
from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.services.whoop import client as whoop_client
from app.services.whoop.types import WhoopAuthError, WhoopRateLimited

_TOKEN = {"access_token": "at", "refresh_token": "rt", "expires_at": 9_999_999_999}


def _sleep(sid, start, end, offset="-03:00", nap=False, state="SCORED", perf=88, stages=None):
    return {
        "id": sid, "start": start, "end": end, "timezone_offset": offset,
        "nap": nap, "score_state": state,
        "score": {
            "sleep_performance_percentage": perf,
            "stage_summary": stages or {
                "total_light_sleep_time_milli": 3 * 3_600_000,
                "total_slow_wave_sleep_time_milli": 2 * 3_600_000,
                "total_rem_sleep_time_milli": 1 * 3_600_000,
                "total_awake_time_milli": 30 * 60_000,
            },
        },
    }


def _recovery(sleep_id, hrv=61.5, rhr=48, score=72, state="SCORED"):
    return {
        "sleep_id": sleep_id, "cycle_id": 1, "score_state": state,
        "score": {"hrv_rmssd_milli": hrv, "resting_heart_rate": rhr, "recovery_score": score},
    }


def _transport(sleeps, recoveries):
    def handler(request: httpx.Request) -> httpx.Response:
        if "/activity/sleep" in request.url.path:
            return httpx.Response(200, json={"records": sleeps, "next_token": None})
        if "/recovery" in request.url.path:
            return httpx.Response(200, json={"records": recoveries, "next_token": None})
        raise AssertionError(f"URL inesperada: {request.url}")
    return httpx.MockTransport(handler)


def test_metric_date_is_the_local_wake_up_day():
    """Dormiu 23h de segunda, acordou 6h de terça => o dado é de TERÇA."""
    sleeps = [_sleep("s1", "2026-07-27T02:00:00Z", "2026-07-28T09:00:00Z")]
    # fim 09:00Z com offset -03:00 => 06:00 local do dia 28
    c = whoop_client.WhoopClient(_TOKEN, transport=_transport(sleeps, [_recovery("s1")]))

    days = c.fetch_days(date(2026, 7, 27), date(2026, 7, 28))

    assert [d.metric_date for d in days] == [date(2026, 7, 28)]


def test_offset_can_change_the_day():
    """Fim às 01:00Z com offset -03:00 é 22:00 do dia ANTERIOR no fuso do atleta."""
    sleeps = [_sleep("s1", "2026-07-27T14:00:00Z", "2026-07-28T01:00:00Z")]
    c = whoop_client.WhoopClient(_TOKEN, transport=_transport(sleeps, [_recovery("s1")]))

    assert c.fetch_days(date(2026, 7, 27), date(2026, 7, 28))[0].metric_date == date(2026, 7, 27)


def test_sleep_hours_sums_only_asleep_stages():
    """3h leve + 2h profundo + 1h REM = 6h. Acordado não é sono."""
    sleeps = [_sleep("s1", "2026-07-27T02:00:00Z", "2026-07-28T09:00:00Z")]
    c = whoop_client.WhoopClient(_TOKEN, transport=_transport(sleeps, [_recovery("s1")]))

    assert c.fetch_days(date(2026, 7, 27), date(2026, 7, 28))[0].snapshot.sleep_hours == 6.0


def test_naps_are_discarded():
    sleeps = [_sleep("s1", "2026-07-28T14:00:00Z", "2026-07-28T15:00:00Z", nap=True)]
    c = whoop_client.WhoopClient(_TOKEN, transport=_transport(sleeps, [_recovery("s1")]))

    assert c.fetch_days(date(2026, 7, 28), date(2026, 7, 28)) == []


def test_unscored_records_are_discarded():
    sleeps = [_sleep("s1", "2026-07-27T02:00:00Z", "2026-07-28T09:00:00Z", state="PENDING_SCORE")]
    c = whoop_client.WhoopClient(_TOKEN, transport=_transport(sleeps, [_recovery("s1")]))

    assert c.fetch_days(date(2026, 7, 27), date(2026, 7, 28)) == []


def test_recovery_without_matching_sleep_is_skipped():
    """Sem o sono correspondente não há data — gravar num dia chutado seria pior."""
    sleeps = [_sleep("s1", "2026-07-27T02:00:00Z", "2026-07-28T09:00:00Z")]
    c = whoop_client.WhoopClient(_TOKEN, transport=_transport(sleeps, [_recovery("SEM-PAR")]))

    day = c.fetch_days(date(2026, 7, 27), date(2026, 7, 28))[0]
    assert day.snapshot.sleep_hours == 6.0
    assert day.snapshot.hrv_ms is None  # sono entrou, recuperação não


def test_pagination_follows_next_token():
    page1 = [_sleep("s1", "2026-07-26T02:00:00Z", "2026-07-27T09:00:00Z")]
    page2 = [_sleep("s2", "2026-07-27T02:00:00Z", "2026-07-28T09:00:00Z")]
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "/recovery" in request.url.path:
            return httpx.Response(200, json={"records": [], "next_token": None})
        if "nextToken=tok2" in str(request.url):
            return httpx.Response(200, json={"records": page2, "next_token": None})
        return httpx.Response(200, json={"records": page1, "next_token": "tok2"})

    c = whoop_client.WhoopClient(_TOKEN, transport=httpx.MockTransport(handler))
    days = c.fetch_days(date(2026, 7, 26), date(2026, 7, 28))

    assert len(days) == 2
    assert any("nextToken=tok2" in u for u in calls)


def test_401_becomes_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_token"})

    c = whoop_client.WhoopClient(_TOKEN, transport=httpx.MockTransport(handler))
    with pytest.raises(WhoopAuthError):
        c.fetch_days(date(2026, 7, 28), date(2026, 7, 28))


def test_429_carries_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"X-RateLimit-Reset": "37"})

    c = whoop_client.WhoopClient(_TOKEN, transport=httpx.MockTransport(handler))
    with pytest.raises(WhoopRateLimited) as exc:
        c.fetch_days(date(2026, 7, 28), date(2026, 7, 28))
    assert exc.value.retry_after_s == 37


def test_authorize_url_carries_state_and_scopes(monkeypatch):
    monkeypatch.setattr(whoop_client.settings, "whoop_client_id", "cid")

    url = whoop_client.authorize_url("st8", "https://app.example/api/whoop/callback")

    assert url.startswith("https://api.prod.whoop.com/oauth/oauth2/auth?")
    assert "state=st8" in url
    assert "read%3Arecovery" in url and "read%3Asleep" in url and "offline" in url
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_whoop/test_client.py -v`
Expected: FAIL na coleta — `ModuleNotFoundError: No module named 'app.services.whoop.client'`

- [ ] **Step 3: Criar os tipos**

`backend/app/services/whoop/types.py`:

```python
"""Tipos e erros do domínio Whoop. Nenhuma exceção da httpx atravessa esta camada."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.services.recovery.merge import RecoverySnapshot


class WhoopAuthError(RuntimeError):
    """Token inválido, expirado ou revogado — exige reautenticação do atleta."""


class WhoopSyncError(RuntimeError):
    """Falha não-autenticação numa chamada (rede, 5xx, corpo inesperado)."""


class WhoopRateLimited(WhoopSyncError):
    """429 da Whoop. ``retry_after_s`` vem do cabeçalho X-RateLimit-Reset."""

    def __init__(self, message: str, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


@dataclass(frozen=True)
class WhoopDay:
    """Um dia de recuperação da Whoop, já resolvido para data local."""

    metric_date: date
    snapshot: RecoverySnapshot
```

- [ ] **Step 4: Implementar o client**

`backend/app/services/whoop/client.py`:

```python
"""Único módulo que fala HTTP com a Whoop (API oficial v2).

Três regras da API que este módulo encapsula, e cuja violação gravaria lixo como
se fosse medição:

1. **Recovery não tem data.** Ela aponta para o sono por ``sleep_id``; a data sai
   do fim do sono, no fuso do próprio registro (``timezone_offset``).
2. **``nap: true`` é cochilo**, não a noite — somar em sleep_hours infla o sono.
3. **``score_state`` diferente de ``SCORED``** significa score ausente ou
   incompleto: descartar, nunca ler como zero.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.recovery.merge import RecoverySnapshot
from app.services.whoop.types import (
    WhoopAuthError,
    WhoopDay,
    WhoopRateLimited,
    WhoopSyncError,
)

log = get_logger(__name__)

AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
API_BASE = "https://api.prod.whoop.com/developer/v2"
SCOPES = "read:recovery read:sleep offline"
PAGE_LIMIT = 25  # máximo aceito pela API
_TIMEOUT = 20.0
_REFRESH_MARGIN_S = 120  # renova antes de vencer, para não perder a corrida


def authorize_url(state: str, redirect_uri: str) -> str:
    """URL para onde o navegador do atleta é enviado no início do OAuth."""
    return f"{AUTH_URL}?" + urlencode({
        "client_id": settings.whoop_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    })


def _token_request(data: dict, transport: httpx.BaseTransport | None) -> dict:
    payload = {
        **data,
        "client_id": settings.whoop_client_id,
        "client_secret": settings.whoop_client_secret,
    }
    try:
        with httpx.Client(timeout=_TIMEOUT, transport=transport) as c:
            r = c.post(TOKEN_URL, data=payload)
    except Exception as exc:  # noqa: BLE001 — nunca vaza exceção da httpx
        raise WhoopSyncError(f"token request failed: {exc}") from exc
    if r.status_code in (400, 401):
        raise WhoopAuthError(f"token rejeitado pela Whoop ({r.status_code})")
    if r.status_code != 200:
        raise WhoopSyncError(f"token request retornou {r.status_code}")
    body = r.json()
    return {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token", data.get("refresh_token")),
        "expires_at": int(time.time()) + int(body.get("expires_in", 3600)),
    }


class WhoopClient:
    """Chamadas autenticadas à Whoop. Renova o token sozinho quando necessário."""

    def __init__(self, token: dict, *, transport: httpx.BaseTransport | None = None) -> None:
        self._token = dict(token)
        self._transport = transport

    @classmethod
    def exchange_code(
        cls, code: str, redirect_uri: str, *, transport: httpx.BaseTransport | None = None
    ) -> dict:
        """Troca o código do callback pelo par de tokens."""
        return _token_request(
            {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
            transport,
        )

    @property
    def token(self) -> dict:
        return dict(self._token)

    def refresh(self) -> dict:
        self._token = _token_request(
            {"grant_type": "refresh_token", "refresh_token": self._token["refresh_token"]},
            self._transport,
        )
        return self.token

    def _ensure_fresh(self) -> None:
        if self._token.get("expires_at", 0) - _REFRESH_MARGIN_S <= int(time.time()):
            self.refresh()

    def _get(self, path: str, params: dict) -> dict:
        self._ensure_fresh()
        try:
            with httpx.Client(timeout=_TIMEOUT, transport=self._transport) as c:
                r = c.get(
                    f"{API_BASE}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {self._token['access_token']}"},
                )
        except Exception as exc:  # noqa: BLE001
            raise WhoopSyncError(f"GET {path} failed: {exc}") from exc
        if r.status_code == 401:
            raise WhoopAuthError(f"GET {path}: token rejeitado")
        if r.status_code == 429:
            reset = r.headers.get("X-RateLimit-Reset")
            raise WhoopRateLimited(
                f"GET {path}: limite de requisições da Whoop",
                retry_after_s=int(reset) if reset and reset.isdigit() else None,
            )
        if r.status_code != 200:
            raise WhoopSyncError(f"GET {path} retornou {r.status_code}")
        try:
            return r.json()
        except ValueError as exc:
            raise WhoopSyncError(f"GET {path}: corpo não é JSON") from exc

    def _paginate(self, path: str, start: date, end: date) -> list[dict]:
        """Percorre as páginas do recurso na janela [start, end]."""
        records: list[dict] = []
        params = {
            "start": f"{start.isoformat()}T00:00:00.000Z",
            # end é exclusivo na API: +1 dia para incluir o último
            "end": f"{(end + timedelta(days=1)).isoformat()}T00:00:00.000Z",
            "limit": PAGE_LIMIT,
        }
        token: str | None = None
        for _ in range(200):  # teto de segurança: 200 páginas x 25 = 5000 registros
            body = self._get(path, {**params, **({"nextToken": token} if token else {})})
            records.extend(body.get("records") or [])
            token = body.get("next_token")
            if not token:
                return records
        log.warning("whoop: %s excedeu o teto de paginação; truncado", path)
        return records

    def fetch_days(self, start: date, end: date) -> list[WhoopDay]:
        """Sonos e recuperações da janela, casados e resolvidos para data local."""
        sleeps = self._paginate("/activity/sleep", start, end)
        recoveries = self._paginate("/recovery", start, end)

        by_sleep_id: dict[str, tuple[date, dict]] = {}
        for s in sleeps:
            if s.get("nap") or s.get("score_state") != "SCORED":
                continue
            day = _local_wake_date(s)
            if day is None:
                continue
            by_sleep_id[str(s["id"])] = (day, s)

        rec_by_sleep = {
            str(r["sleep_id"]): r
            for r in recoveries
            if r.get("score_state") == "SCORED" and r.get("sleep_id")
        }

        out: list[WhoopDay] = []
        for sleep_id, (day, sleep) in sorted(by_sleep_id.items(), key=lambda kv: kv[1][0]):
            rec = rec_by_sleep.get(sleep_id, {})
            score = rec.get("score") or {}
            out.append(WhoopDay(
                metric_date=day,
                snapshot=RecoverySnapshot(
                    hrv_ms=score.get("hrv_rmssd_milli"),
                    resting_hr=score.get("resting_heart_rate"),
                    recovery_score=score.get("recovery_score"),
                    sleep_hours=_asleep_hours(sleep),
                    sleep_score=(sleep.get("score") or {}).get("sleep_performance_percentage"),
                ),
            ))
        return out


def _local_wake_date(sleep: dict) -> date | None:
    """Data local do fim do sono — o dia cujo treino essa recuperação informa."""
    end, offset = sleep.get("end"), sleep.get("timezone_offset")
    if not end:
        return None
    try:
        dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        if offset:
            sign = -1 if str(offset).startswith("-") else 1
            hh, _, mm = str(offset).lstrip("+-").partition(":")
            dt = dt + sign * timedelta(hours=int(hh), minutes=int(mm or 0))
        return dt.date()
    except (ValueError, TypeError):
        log.warning("whoop: sono com end/offset ilegível: %r / %r", end, offset)
        return None


def _asleep_hours(sleep: dict) -> float | None:
    """Só os estágios dormindo: leve + profundo + REM. Acordado não é sono."""
    stages = ((sleep.get("score") or {}).get("stage_summary")) or {}
    keys = (
        "total_light_sleep_time_milli",
        "total_slow_wave_sleep_time_milli",
        "total_rem_sleep_time_milli",
    )
    values = [stages.get(k) for k in keys]
    if all(v is None for v in values):
        return None
    return round(sum(v or 0 for v in values) / 3_600_000, 2)
```

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_whoop/test_client.py -v`
Expected: PASS (10 testes)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/whoop/types.py backend/app/services/whoop/client.py backend/app/tests/test_whoop/test_client.py
git commit -m "feat(whoop): client da API v2 (OAuth, paginacao, data local do sono)"
```

---

### Task 5: sync service + client falso

**Files:**
- Create: `backend/app/services/whoop/fake_client.py`, `backend/app/services/whoop/sync_service.py`
- Test: `backend/app/tests/test_whoop/test_sync.py`

**Interfaces:**
- Consumes: `WhoopClient.fetch_days` (Task 4), `merge_into` (Task 2), `WhoopConnection` (Task 3), `token_store` (Task 1).
- Produces:
  - `app.services.whoop.sync_service.sync_athlete(session, ctx, athlete_id, *, client, days: int) -> WhoopSyncReport` — `WhoopSyncReport` é dataclass com `days_written: int` e `days_seen: int`.
  - `app.services.whoop.fake_client.FakeWhoopClient(days: list[WhoopDay], *, raise_on_fetch: Exception | None = None)` com a mesma superfície usada pelo sync (`fetch_days`, `token`).

- [ ] **Step 1: Escrever os testes que falham**

`backend/app/tests/test_whoop/test_sync.py`:

```python
"""O sync é idempotente e nunca deixa a conexão mentir sobre o próprio estado.

Duas regressões que estes testes travam:
- rodar duas vezes a mesma janela não pode duplicar nem alterar nada na segunda
- token rejeitado tem de virar NEEDS_REAUTH, senão o job tenta para sempre em
  silêncio e o atleta nunca sabe que precisa reconectar
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models.enums import WhoopConnectionStatus
from app.models.metrics import RecoveryMetric
from app.models.whoop import WhoopConnection
from app.services.recovery.merge import RecoverySnapshot
from app.services.whoop.fake_client import FakeWhoopClient
from app.services.whoop.sync_service import sync_athlete
from app.services.whoop.types import WhoopAuthError, WhoopDay


def _days():
    return [
        WhoopDay(date(2026, 7, 27), RecoverySnapshot(hrv_ms=61.5, resting_hr=48, sleep_hours=6.0)),
        WhoopDay(date(2026, 7, 28), RecoverySnapshot(hrv_ms=58.0, resting_hr=50, sleep_hours=7.1)),
    ]


async def _conn(session, athlete):
    c = WhoopConnection(
        athlete_id=athlete.id, tenant_id=athlete.tenant_id,
        status=WhoopConnectionStatus.CONNECTED, encrypted_token=None,
    )
    session.add(c)
    await session.flush()
    return c


async def test_writes_one_row_per_day(session, athlete_ctx, two_athletes):
    a, _ = two_athletes
    await _conn(session, a)

    report = await sync_athlete(
        session, athlete_ctx, a.id, client=FakeWhoopClient(_days()), days=3
    )

    rows = (await session.execute(
        select(RecoveryMetric).where(RecoveryMetric.athlete_id == a.id)
    )).scalars().all()
    assert report.days_written == 2
    assert {r.metric_date for r in rows} == {date(2026, 7, 27), date(2026, 7, 28)}
    assert all(r.source == "whoop" for r in rows)


async def test_second_run_changes_nothing(session, athlete_ctx, two_athletes):
    a, _ = two_athletes
    await _conn(session, a)
    await sync_athlete(session, athlete_ctx, a.id, client=FakeWhoopClient(_days()), days=3)

    report = await sync_athlete(
        session, athlete_ctx, a.id, client=FakeWhoopClient(_days()), days=3
    )

    rows = (await session.execute(
        select(RecoveryMetric).where(RecoveryMetric.athlete_id == a.id)
    )).scalars().all()
    assert len(rows) == 2
    assert report.days_written == 0  # nada novo escrito


async def test_auth_error_marks_needs_reauth(session, athlete_ctx, two_athletes):
    a, _ = two_athletes
    conn = await _conn(session, a)
    client = FakeWhoopClient([], raise_on_fetch=WhoopAuthError("token revogado"))

    with pytest.raises(WhoopAuthError):
        await sync_athlete(session, athlete_ctx, a.id, client=client, days=3)

    assert conn.status is WhoopConnectionStatus.NEEDS_REAUTH
    assert "token revogado" in (conn.last_error or "")


async def test_does_not_touch_another_athletes_rows(session, athlete_ctx, two_athletes):
    a, b = two_athletes
    await _conn(session, a)

    await sync_athlete(session, athlete_ctx, a.id, client=FakeWhoopClient(_days()), days=3)

    other = (await session.execute(
        select(RecoveryMetric).where(RecoveryMetric.athlete_id == b.id)
    )).scalars().all()
    assert other == []
```

**Nota sobre fixtures:** `session` e `two_athletes` existem em `backend/app/tests/conftest.py`. `athlete_ctx` é a fixture de `TenantContext` de atleta — confirme o nome exato no conftest (há `TenantContext(...)` construído nas linhas 63-69) e ajuste a assinatura se o nome diferir.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_whoop/test_sync.py -v`
Expected: FAIL na coleta — `ModuleNotFoundError: No module named 'app.services.whoop.fake_client'`

- [ ] **Step 3: Criar o client falso**

`backend/app/services/whoop/fake_client.py`:

```python
"""Client determinístico da Whoop para teste offline.

Mesma razão do fake_client do Garmin: o sync inteiro precisa ser testável sem
rede e sem conta real.
"""
from __future__ import annotations

from datetime import date

from app.services.whoop.types import WhoopDay


class FakeWhoopClient:
    def __init__(self, days: list[WhoopDay], *, raise_on_fetch: Exception | None = None) -> None:
        self._days = days
        self._raise = raise_on_fetch
        self.calls: list[tuple[date, date]] = []
        self.token = {"access_token": "fake", "refresh_token": "fake", "expires_at": 9_999_999_999}

    def fetch_days(self, start: date, end: date) -> list[WhoopDay]:
        self.calls.append((start, end))
        if self._raise is not None:
            raise self._raise
        return [d for d in self._days if start <= d.metric_date <= end]
```

- [ ] **Step 4: Implementar o sync service**

`backend/app/services/whoop/sync_service.py`:

```python
"""Orquestra o pull da Whoop. Recebe o client por injeção, então testa offline.

Grava via ``merge_into``, que é onde vive a precedência entre fontes — este
módulo não sabe nada sobre o Garmin.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.models.enums import WhoopConnectionStatus
from app.models.metrics import RecoveryMetric
from app.models.whoop import WhoopConnection
from app.services.recovery.merge import merge_into
from app.services.whoop import token_store
from app.services.whoop.types import WhoopAuthError

log = get_logger(__name__)
SOURCE = "whoop"


@dataclass
class WhoopSyncReport:
    days_seen: int = 0
    days_written: int = 0


async def _get_connection(session: AsyncSession, athlete_id: uuid.UUID) -> WhoopConnection | None:
    return (await session.execute(
        select(WhoopConnection).where(
            WhoopConnection.athlete_id == athlete_id,
            WhoopConnection.deleted_at.is_(None),
        )
    )).scalar_one_or_none()


async def sync_athlete(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
    *,
    client,
    days: int,
) -> WhoopSyncReport:
    """Puxa os últimos ``days`` dias e grava em recovery_metrics."""
    conn = await _get_connection(session, athlete_id)
    if conn is None:
        raise WhoopAuthError("atleta não tem conexão Whoop")

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)

    try:
        fetched = client.fetch_days(start, today)
    except WhoopAuthError as exc:
        conn.status = WhoopConnectionStatus.NEEDS_REAUTH
        conn.last_error = str(exc)[:512]
        await session.flush()
        raise

    report = WhoopSyncReport(days_seen=len(fetched))
    for day in fetched:
        existing = (await session.execute(
            select(RecoveryMetric).where(
                RecoveryMetric.athlete_id == athlete_id,
                RecoveryMetric.metric_date == day.metric_date,
            )
        )).scalar_one_or_none()
        if existing is None:
            existing = RecoveryMetric(
                athlete_id=athlete_id, tenant_id=ctx.tenant_id, metric_date=day.metric_date
            )
            session.add(existing)
        if merge_into(existing, day.snapshot, SOURCE):
            report.days_written += 1

    # O token pode ter sido renovado durante o fetch — persiste o novo.
    if token_store.is_enabled():
        conn.encrypted_token = token_store.encrypt(client.token)
    conn.last_sync_at = datetime.now(timezone.utc)
    conn.last_error = None
    await session.flush()
    log.info(
        "whoop: atleta=%s dias_vistos=%d dias_escritos=%d",
        athlete_id, report.days_seen, report.days_written,
    )
    return report
```

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_whoop/test_sync.py -v`
Expected: PASS (4 testes)

- [ ] **Step 6: Rodar a suíte inteira**

Run: `bash <scratchpad>/vm-test.sh`
Expected: **551 passed** (534 + 3 modelo + 10 client + 4 sync), 1 warning conhecido.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/whoop/fake_client.py backend/app/services/whoop/sync_service.py backend/app/tests/test_whoop/test_sync.py
git commit -m "feat(whoop): sync service idempotente com client falso para teste offline"
```

---

### Task 6: jobs e agendamento no beat

**Files:**
- Create: `backend/app/jobs/whoop_job.py`
- Modify: `backend/app/jobs/celery_app.py`
- Test: `backend/app/tests/test_whoop/test_job_wiring.py`

**Interfaces:**
- Consumes: `sync_athlete` (Task 5), `WhoopClient` (Task 4), `token_store` (Task 1), `WhoopConnection` (Task 3).
- Produces: tasks registradas com os nomes `whoop_sync`, `whoop_backfill`, `whoop_beat_sync_all`; entrada `"whoop-daily-sync"` no `beat_schedule` com `crontab(hour=8, minute=0)`.

- [ ] **Step 1: Escrever os testes que falham**

`backend/app/tests/test_whoop/test_job_wiring.py`:

```python
"""Sem a entrada no beat o sync nunca roda, e a falha é silenciosa.

O cron às 08:00 UTC (05:00 no Brasil) existe para o dado da noite estar pronto
antes de o atleta gerar o treino do dia. Uma janela em intervalo de 24h, como a
do garmin-daily-sync, não garante hora — por isso este é crontab.
"""
from __future__ import annotations

from celery.schedules import crontab

from app.jobs.celery_app import celery


def test_whoop_sync_is_scheduled_at_8_utc():
    entry = celery.conf.beat_schedule["whoop-daily-sync"]
    assert entry["task"] == "whoop_beat_sync_all"
    assert entry["schedule"] == crontab(hour=8, minute=0)


def test_existing_schedules_survive():
    """A entrada nova não pode substituir as que já existem."""
    keys = set(celery.conf.beat_schedule)
    assert {"garmin-daily-sync", "monitoring-heartbeat"} <= keys
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_whoop/test_job_wiring.py -v`
Expected: FAIL — `KeyError: 'whoop-daily-sync'`

- [ ] **Step 3: Criar as tasks**

`backend/app/jobs/whoop_job.py`:

```python
"""Tasks da Whoop: sync de um atleta, backfill inicial e o enfileirador do beat.

O backfill de 180 dias roda uma vez, na conexão. O sync diário usa janela de 3
dias porque a Whoop corrige e completa registros depois de publicá-los.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.tenant import TenantContext
from app.jobs._run import run_async
from app.models.enums import Role, WhoopConnectionStatus
from app.models.whoop import WhoopConnection
from app.services.whoop import token_store
from app.services.whoop.client import WhoopClient
from app.services.whoop.sync_service import sync_athlete
from app.services.whoop.types import WhoopSyncError

DAILY_WINDOW_DAYS = 3
BACKFILL_DAYS = 180


async def _do_sync(athlete_id: str, tenant_id: str, days: int, mark_backfilled: bool) -> dict:
    aid = uuid.UUID(athlete_id)
    ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)
    async with AsyncSessionLocal() as session:
        conn = (await session.execute(
            select(WhoopConnection).where(
                WhoopConnection.athlete_id == aid,
                WhoopConnection.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if conn is None or not conn.encrypted_token:
            return {"skipped": "sem conexão"}
        client = WhoopClient(token_store.decrypt(conn.encrypted_token))
        report = await sync_athlete(session, ctx, aid, client=client, days=days)
        if mark_backfilled:
            conn.backfilled_at = datetime.now(timezone.utc)
        await session.commit()
        return {"days_seen": report.days_seen, "days_written": report.days_written}


def sync_whoop(athlete_id: str, tenant_id: str) -> dict:
    """Task: janela curta, usada pelo beat e pelo botão 'sincronizar agora'."""
    return run_async(_do_sync(athlete_id, tenant_id, DAILY_WINDOW_DAYS, False))


def backfill_whoop(athlete_id: str, tenant_id: str) -> dict:
    """Task: carga inicial de 180 dias, disparada uma vez na conexão."""
    return run_async(_do_sync(athlete_id, tenant_id, BACKFILL_DAYS, True))


async def _enqueue_all_connected() -> int:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(WhoopConnection).where(
                WhoopConnection.status == WhoopConnectionStatus.CONNECTED,
                WhoopConnection.deleted_at.is_(None),
            )
        )
        count = 0
        for conn in rows.scalars().all():
            sync_whoop.delay(str(conn.athlete_id), conn.tenant_id)
            count += 1
        return count


def beat_sync_all() -> int:
    """Beat entry-point: enfileira o sync de cada atleta conectado."""
    return run_async(_enqueue_all_connected())


try:
    from app.jobs.celery_app import celery

    sync_whoop = celery.task(  # type: ignore[assignment]
        name="whoop_sync",
        autoretry_for=(WhoopSyncError,),
        retry_backoff=True,
        max_retries=3,
    )(sync_whoop)
    backfill_whoop = celery.task(  # type: ignore[assignment]
        name="whoop_backfill",
        autoretry_for=(WhoopSyncError,),
        retry_backoff=True,
        max_retries=3,
    )(backfill_whoop)
    beat_sync_all = celery.task(name="whoop_beat_sync_all")(beat_sync_all)  # type: ignore[assignment]
except Exception:  # noqa: BLE001 — importável sem broker (testes)
    pass
```

- [ ] **Step 4: Ligar no beat**

Em `backend/app/jobs/celery_app.py`: acrescentar `whoop_job` à linha de import dos jobs, importar `crontab` e adicionar a entrada:

```python
from celery.schedules import crontab  # noqa: E402

from app.jobs import (  # noqa: E402,F401
    import_job, metrics_job, profile_job, garmin_job, health_job, whoop_job,
)

...

    "whoop-daily-sync": {
        "task": "whoop_beat_sync_all",
        # Hora fixa: 08:00 UTC = 05:00 no Brasil. O dado da noite precisa estar
        # pronto antes de o atleta gerar o treino do dia.
        "schedule": crontab(hour=8, minute=0),
    },
```

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_whoop/test_job_wiring.py -v`
Expected: PASS (2 testes)

- [ ] **Step 6: Commit**

```bash
git add backend/app/jobs/whoop_job.py backend/app/jobs/celery_app.py backend/app/tests/test_whoop/test_job_wiring.py
git commit -m "feat(whoop): tasks de sync/backfill e cron diario as 08:00 UTC"
```

---

### Task 7: rotas da API e assinatura do `state`

**Files:**
- Create: `backend/app/services/whoop/oauth_state.py`, `backend/app/schemas/whoop.py`, `backend/app/api/routes/whoop.py`
- Modify: onde os routers são registrados (mesmo lugar do router do Garmin)
- Test: `backend/app/tests/test_whoop/test_oauth_state.py`, `backend/app/tests/test_whoop/test_api.py`

**Interfaces:**
- Consumes: `authorize_url`, `WhoopClient.exchange_code` (Task 4), `token_store` (Task 1), `WhoopConnection` (Task 3), `backfill_whoop` (Task 6).
- Produces:
  - `app.services.whoop.oauth_state.issue(athlete_id: uuid.UUID) -> str` e `verify(state: str, athlete_id: uuid.UUID) -> None` (levanta `WhoopStateError`)
  - Rotas: `GET /whoop/status`, `POST /whoop/authorize`, `POST /whoop/callback`, `POST /whoop/sync`, `DELETE /whoop/connection`

- [ ] **Step 1: Escrever os testes do `state`**

`backend/app/tests/test_whoop/test_oauth_state.py`:

```python
"""O state amarra o callback ao atleta certo e expira.

Sem isso, um atacante induz o atleta logado a abrir um callback com o `code` da
conta Whoop do atacante — e os dados de saúde de um estranho passam a alimentar
o treino do atleta. O state assinado é o que impede.
"""
from __future__ import annotations

import time
import uuid

import pytest

from app.services.whoop import oauth_state


def test_round_trip_accepts_the_same_athlete(monkeypatch):
    monkeypatch.setattr(oauth_state.settings, "jwt_secret_key", "segredo-de-teste")
    aid = uuid.uuid4()

    oauth_state.verify(oauth_state.issue(aid), aid)  # não levanta


def test_rejects_a_different_athlete(monkeypatch):
    monkeypatch.setattr(oauth_state.settings, "jwt_secret_key", "segredo-de-teste")
    state = oauth_state.issue(uuid.uuid4())

    with pytest.raises(oauth_state.WhoopStateError):
        oauth_state.verify(state, uuid.uuid4())


def test_rejects_tampered_state(monkeypatch):
    monkeypatch.setattr(oauth_state.settings, "jwt_secret_key", "segredo-de-teste")
    aid = uuid.uuid4()
    state = oauth_state.issue(aid)

    with pytest.raises(oauth_state.WhoopStateError):
        oauth_state.verify(state[:-4] + "AAAA", aid)


def test_rejects_expired_state(monkeypatch):
    monkeypatch.setattr(oauth_state.settings, "jwt_secret_key", "segredo-de-teste")
    aid = uuid.uuid4()
    monkeypatch.setattr(time, "time", lambda: 1_000_000)
    state = oauth_state.issue(aid)
    monkeypatch.setattr(time, "time", lambda: 1_000_000 + oauth_state.TTL_S + 1)

    with pytest.raises(oauth_state.WhoopStateError):
        oauth_state.verify(state, aid)
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_whoop/test_oauth_state.py -v`
Expected: FAIL na coleta — `ModuleNotFoundError: No module named 'app.services.whoop.oauth_state'`

- [ ] **Step 3: Implementar o `state`**

`backend/app/services/whoop/oauth_state.py`:

```python
"""State assinado do OAuth da Whoop: amarra o callback ao atleta e expira.

Reusa ``settings.jwt_secret_key`` — é o mesmo segredo que já autentica sessão
neste servidor, e um segundo segredo aqui só criaria mais uma coisa para rotacionar.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid

from app.core.config import settings

TTL_S = 600  # 10 minutos


class WhoopStateError(RuntimeError):
    """State ausente, adulterado, de outro atleta ou expirado."""


def _sign(payload: str) -> str:
    mac = hmac.new(settings.jwt_secret_key.encode(), payload.encode(), hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest()).decode().rstrip("=")


def issue(athlete_id: uuid.UUID) -> str:
    payload = f"{athlete_id}.{int(time.time())}"
    return f"{base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')}.{_sign(payload)}"


def verify(state: str, athlete_id: uuid.UUID) -> None:
    try:
        raw, sig = state.split(".", 1)
        padded = raw + "=" * (-len(raw) % 4)
        payload = base64.urlsafe_b64decode(padded.encode()).decode()
        claimed_id, _, issued_at = payload.partition(".")
    except (ValueError, UnicodeDecodeError) as exc:
        raise WhoopStateError("state ilegível") from exc

    if not hmac.compare_digest(sig, _sign(payload)):
        raise WhoopStateError("assinatura do state inválida")
    if claimed_id != str(athlete_id):
        raise WhoopStateError("state pertence a outro atleta")
    try:
        if int(issued_at) + TTL_S < int(time.time()):
            raise WhoopStateError("state expirado")
    except ValueError as exc:
        raise WhoopStateError("timestamp do state inválido") from exc
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_whoop/test_oauth_state.py -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Escrever os testes da API**

`backend/app/tests/test_whoop/test_api.py` — cobre, no estilo de `app/tests/test_garmin/test_api.py` (siga esse arquivo para os fixtures de client autenticado):

```python
"""A integração desligada não pode aparecer meio-ligada, e o callback não pode
aceitar código sem state válido.
"""
from __future__ import annotations


async def test_status_503_when_not_configured(client_athlete, monkeypatch):
    monkeypatch.setattr("app.api.routes.whoop.settings.whoop_client_id", "")

    r = await client_athlete.get("/api/v1/whoop/status")

    assert r.status_code == 503


async def test_status_reports_disconnected_when_configured(client_athlete, monkeypatch):
    monkeypatch.setattr("app.api.routes.whoop.settings.whoop_client_id", "cid")
    monkeypatch.setattr("app.api.routes.whoop.settings.whoop_client_secret", "sec")

    r = await client_athlete.get("/api/v1/whoop/status")

    assert r.status_code == 200
    assert r.json()["status"] == "DISCONNECTED"


async def test_authorize_returns_url_with_state(client_athlete, monkeypatch):
    monkeypatch.setattr("app.api.routes.whoop.settings.whoop_client_id", "cid")
    monkeypatch.setattr("app.api.routes.whoop.settings.whoop_client_secret", "sec")

    r = await client_athlete.post("/api/v1/whoop/authorize")

    assert r.status_code == 200
    assert "state=" in r.json()["authorize_url"]


async def test_callback_rejects_bad_state(client_athlete, monkeypatch):
    monkeypatch.setattr("app.api.routes.whoop.settings.whoop_client_id", "cid")
    monkeypatch.setattr("app.api.routes.whoop.settings.whoop_client_secret", "sec")

    r = await client_athlete.post(
        "/api/v1/whoop/callback", json={"code": "abc", "state": "invalido.xx"}
    )

    assert r.status_code == 403
```

- [ ] **Step 6: Implementar schemas e rotas**

`backend/app/schemas/whoop.py`:

```python
"""Contratos da API da integração Whoop."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WhoopStatusRead(BaseModel):
    status: str
    last_sync_at: datetime | None = None
    last_error: str | None = None
    connected_at: datetime | None = None


class WhoopAuthorizeRead(BaseModel):
    authorize_url: str


class WhoopCallbackRequest(BaseModel):
    code: str
    state: str
```

`backend/app/api/routes/whoop.py` — cinco rotas, todas com o mesmo guarda de feature:

```python
"""Rotas da integração Whoop: autorizar, callback, status, sincronizar, desconectar.

Feature desligada (client_id/secret vazios) responde 503 em todas — o card do web
some e nada quebra.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.models.enums import WhoopConnectionStatus
from app.models.whoop import WhoopConnection
from app.schemas.whoop import (
    WhoopAuthorizeRead,
    WhoopCallbackRequest,
    WhoopStatusRead,
)
from app.services.whoop import oauth_state, token_store
from app.services.whoop.client import WhoopClient, authorize_url
from app.services.whoop.types import WhoopAuthError, WhoopSyncError

router = APIRouter(prefix="/whoop", tags=["whoop"])
log = get_logger(__name__)


def _require_enabled() -> None:
    if not (settings.whoop_client_id and settings.whoop_client_secret):
        raise HTTPException(status_code=503, detail="whoop_disabled")


def _redirect_uri() -> str:
    return f"https://{settings.site_address}/api/whoop/callback"


async def _connection(db: AsyncSession, athlete_id) -> WhoopConnection | None:
    return (await db.execute(
        select(WhoopConnection).where(
            WhoopConnection.athlete_id == athlete_id,
            WhoopConnection.deleted_at.is_(None),
        )
    )).scalar_one_or_none()


@router.get("/status", response_model=WhoopStatusRead)
async def status(ctx: TenantContext = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    _require_enabled()
    conn = await _connection(db, ctx.athlete_id)
    if conn is None:
        return WhoopStatusRead(status=WhoopConnectionStatus.DISCONNECTED.value)
    return WhoopStatusRead(
        status=conn.status.value,
        last_sync_at=conn.last_sync_at,
        last_error=conn.last_error,
        connected_at=conn.connected_at,
    )


@router.post("/authorize", response_model=WhoopAuthorizeRead)
async def authorize(ctx: TenantContext = Depends(get_tenant)):
    _require_enabled()
    state = oauth_state.issue(ctx.athlete_id)
    return WhoopAuthorizeRead(authorize_url=authorize_url(state, _redirect_uri()))


@router.post("/callback", response_model=WhoopStatusRead)
async def callback(
    body: WhoopCallbackRequest,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    try:
        oauth_state.verify(body.state, ctx.athlete_id)
    except oauth_state.WhoopStateError as exc:
        raise HTTPException(status_code=403, detail="invalid_state") from exc
    if not token_store.is_enabled():
        raise HTTPException(status_code=503, detail="whoop_token_key_missing")

    try:
        token = WhoopClient.exchange_code(body.code, _redirect_uri())
    except WhoopAuthError as exc:
        # A Whoop limita 10 membros em app não aprovado; a troca de token é onde
        # o 11º atleta bate. Mensagem específica para não depurar isso às cegas.
        log.warning("whoop: troca de código falhou: %s", exc)
        raise HTTPException(status_code=403, detail="whoop_authorization_failed") from exc
    except WhoopSyncError as exc:
        raise HTTPException(status_code=502, detail="whoop_unavailable") from exc

    conn = await _connection(db, ctx.athlete_id)
    if conn is None:
        conn = WhoopConnection(athlete_id=ctx.athlete_id, tenant_id=ctx.tenant_id)
        db.add(conn)
    conn.encrypted_token = token_store.encrypt(token)
    conn.status = WhoopConnectionStatus.CONNECTED
    conn.connected_at = datetime.now(timezone.utc)
    conn.last_error = None
    await db.commit()

    if conn.backfilled_at is None:
        try:
            from app.jobs.whoop_job import backfill_whoop

            backfill_whoop.delay(str(ctx.athlete_id), ctx.tenant_id)
        except Exception:  # noqa: BLE001 — broker fora nunca derruba a conexão
            log.exception("whoop: enfileirar backfill falhou; conexão mantida")

    return WhoopStatusRead(
        status=conn.status.value, connected_at=conn.connected_at,
    )


@router.post("/sync", status_code=202)
async def sync_now(ctx: TenantContext = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    _require_enabled()
    conn = await _connection(db, ctx.athlete_id)
    if conn is None or conn.status is not WhoopConnectionStatus.CONNECTED:
        raise HTTPException(status_code=409, detail="not_connected")
    from app.jobs.whoop_job import sync_whoop

    task = sync_whoop.delay(str(ctx.athlete_id), ctx.tenant_id)
    return {"task_id": task.id}


@router.delete("/connection", status_code=204)
async def disconnect(ctx: TenantContext = Depends(get_tenant), db: AsyncSession = Depends(get_db)):
    _require_enabled()
    conn = await _connection(db, ctx.athlete_id)
    if conn is not None:
        conn.status = WhoopConnectionStatus.DISCONNECTED
        conn.encrypted_token = None  # o token sai do banco na hora
        await db.commit()
```

Registrar o router no mesmo arquivo onde o do Garmin é registrado.

- [ ] **Step 7: Rodar os testes da API**

Run: `bash <scratchpad>/vm-test.sh app/tests/test_whoop -v`
Expected: PASS. Se os fixtures de client autenticado tiverem nome diferente, ajuste conforme `app/tests/test_garmin/test_api.py`.

- [ ] **Step 8: Rodar a suíte inteira e commitar**

Run: `bash <scratchpad>/vm-test.sh`
Expected: **559 passed** (551 + 4 state + 4 api), 1 warning conhecido.

```bash
git add backend/app/services/whoop/oauth_state.py backend/app/schemas/whoop.py backend/app/api/routes/whoop.py backend/app/api/ backend/app/tests/test_whoop
git commit -m "feat(whoop): rotas de OAuth, status, sync e desconexao com state assinado"
```

---

### Task 8: card no web e rota de callback

**Files:**
- Create: `web/components/importar/WhoopCard.tsx`, `web/app/api/whoop/callback/route.ts`
- Modify: `web/lib/types.ts` (tipo `WhoopStatus`), `web/lib/hooks.ts` (hook `useWhoopStatus`), `web/app/(app)/importar/page.tsx` (montar o card ao lado do `GarminCard`)
- Test: `web/components/importar/__tests__/WhoopCard.test.tsx`

**Interfaces:**
- Consumes: as cinco rotas da Task 7, via `apiFetch` (`web/lib/api.ts`) e o proxy `/api/proxy/...`.
- Produces:
  - `WhoopStatus` em `web/lib/types.ts`: `{ status: 'CONNECTED' | 'NEEDS_REAUTH' | 'DISCONNECTED'; last_sync_at: string | null; last_error: string | null; connected_at: string | null }`
  - `useWhoopStatus()` em `web/lib/hooks.ts`, no mesmo formato de `useGarminStatus` (SWR, devolvendo `{data, error, isLoading, mutate}`)
  - `WhoopCard`. Nenhum outro componente depende dele.

- [ ] **Step 1: Escrever os testes que falham**

`web/components/importar/__tests__/WhoopCard.test.tsx` — **espelha exatamente** o padrão de `GarminCard.test.tsx`: mocka o hook SWR e `apiFetch`, e usa `container` vazio (não testid) para o caso 503.

```tsx
/**
 * O card some quando a integração está desligada, e o erro de limite de membros
 * precisa dizer o que é: a Whoop recusa o 11º atleta enquanto o app não for
 * aprovado, e um "falha ao conectar" genérico manda o operador depurar às cegas.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { WhoopCard } from '@/components/importar/WhoopCard'
import { useWhoopStatus } from '@/lib/hooks'
import { apiFetch } from '@/lib/api'
import type { WhoopStatus } from '@/lib/types'

vi.mock('@/lib/hooks', () => ({ useWhoopStatus: vi.fn() }))
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

const statusOf = (over: Partial<WhoopStatus>): WhoopStatus => ({
  status: 'DISCONNECTED', last_sync_at: null, last_error: null, connected_at: null, ...over,
})

function mockHook(v: { data?: WhoopStatus; error?: unknown; isLoading?: boolean }) {
  ;(useWhoopStatus as Mock).mockReturnValue({
    data: v.data, error: v.error, isLoading: v.isLoading ?? false, mutate: vi.fn(),
  })
}

beforeEach(() => vi.clearAllMocks())

describe('WhoopCard', () => {
  it('não renderiza nada quando a feature está desligada (503)', () => {
    mockHook({ error: { status: 503 } })
    const { container } = render(<WhoopCard />)
    expect(container).toBeEmptyDOMElement()
  })

  it('mostra Conectar quando desconectado', () => {
    mockHook({ data: statusOf({ status: 'DISCONNECTED' }) })
    render(<WhoopCard />)
    expect(screen.getByRole('button', { name: /conectar/i })).toBeInTheDocument()
  })

  it('mostra Reconectar quando o token caiu', () => {
    mockHook({ data: statusOf({ status: 'NEEDS_REAUTH' }) })
    render(<WhoopCard />)
    expect(screen.getByRole('button', { name: /reconectar/i })).toBeInTheDocument()
  })

  it('mostra Sincronizar agora quando conectado', () => {
    mockHook({ data: statusOf({ status: 'CONNECTED', connected_at: '2026-07-29T12:00:00Z' }) })
    render(<WhoopCard />)
    expect(screen.getByRole('button', { name: /sincronizar agora/i })).toBeInTheDocument()
  })

  it('explica o limite de membros em vez de erro genérico', async () => {
    mockHook({ data: statusOf({ status: 'DISCONNECTED' }) })
    ;(apiFetch as Mock).mockResolvedValue(
      jsonRes({ detail: 'whoop_authorization_failed' }, 403),
    )
    render(<WhoopCard />)

    fireEvent.click(screen.getByRole('button', { name: /conectar/i }))

    await waitFor(() =>
      expect(screen.getByText(/limita 10 atletas/i)).toBeInTheDocument(),
    )
  })
})
```

**Nota:** o último teste assume que o clique em "Conectar" chama `apiFetch('whoop/authorize')` e trata resposta de erro exibindo a mensagem mapeada. Se o fluxo do card diferir (por exemplo, o erro chegando pela query string `?motivo=` do redirect em vez da chamada), ajuste o teste para o caminho real — **a asserção que importa é que o texto do limite de membros apareça em algum caminho de erro**, não qual chamada o produziu.

- [ ] **Step 2: Rodar e confirmar que falha**

Run (no host, não na VM — o web roda com npm): `cd web && npx vitest run components/importar/__tests__/WhoopCard.test.tsx`
Expected: FAIL — módulo `WhoopCard` não existe.

- [ ] **Step 3: Criar a rota de callback no web**

`web/app/api/whoop/callback/route.ts` — recebe o redirect da Whoop no navegador (com a sessão do atleta no cookie), repassa ao backend e volta para `/importar`:

```ts
import { NextRequest, NextResponse } from 'next/server'

export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get('code')
  const state = req.nextUrl.searchParams.get('state')
  const base = new URL('/importar', req.nextUrl.origin)

  if (!code || !state) {
    base.searchParams.set('whoop', 'erro')
    return NextResponse.redirect(base)
  }

  const res = await fetch(`${process.env.API_BASE_URL}/whoop/callback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', cookie: req.headers.get('cookie') ?? '' },
    body: JSON.stringify({ code, state }),
  })

  base.searchParams.set('whoop', res.ok ? 'ok' : 'erro')
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    if (body?.detail) base.searchParams.set('motivo', String(body.detail))
  }
  return NextResponse.redirect(base)
}
```

**Atenção:** confirme como as outras rotas de `web/app/api/` repassam a autenticação ao backend (ver `web/app/api/auth/google/route.ts` e `web/app/api/proxy/[...path]`) e siga o mesmo mecanismo — se elas convertem o cookie em header `Authorization`, faça igual em vez de repassar o cookie cru.

- [ ] **Step 4: Criar o card**

`web/components/importar/WhoopCard.tsx` — estados: ausente (503), desconectado, conectado, precisa reautenticar. Botões: **Conectar** (chama `whoop/authorize` e manda o navegador para a URL devolvida), **Sincronizar agora** (`whoop/sync`), **Desconectar** (`DELETE whoop/connection`). Mostra `last_sync_at` e, quando houver, `last_error`.

Mapa de mensagens de erro — a linha do limite de membros é o motivo desta tabela existir:

```tsx
const ERRO: Record<string, string> = {
  whoop_authorization_failed:
    'A Whoop recusou a autorização. Enquanto o app não for aprovado, a Whoop limita 10 atletas conectados — se esse limite foi atingido, é preciso desconectar alguém ou pedir aprovação.',
  whoop_unavailable: 'A Whoop não respondeu. Tente em alguns minutos.',
  whoop_token_key_missing: 'Integração incompleta no servidor (chave de criptografia ausente).',
  invalid_state: 'A autorização expirou. Clique em Conectar novamente.',
}
```

Montar em `web/app/(app)/importar/page.tsx` ao lado do `GarminCard`.

- [ ] **Step 5: Rodar os testes do web**

Run: `cd web && npx vitest run components/importar/__tests__/WhoopCard.test.tsx`
Expected: PASS (4 testes)

- [ ] **Step 6: Rodar a suíte do web inteira**

Run: `cd web && npx vitest run`
Expected: PASS, sem regressão nos testes existentes.

- [ ] **Step 7: Commit**

```bash
git add web/components/importar/WhoopCard.tsx web/app/api/whoop web/app/\(app\)/importar/page.tsx web/components/importar/__tests__/WhoopCard.test.tsx
git commit -m "feat(web): card de conexao Whoop e rota de callback do OAuth"
```

---

### Task 9: runbook de operação

**Files:**
- Create: `docs/ops/integracao-whoop.md`

Sem teste automatizado: é o que o operador faz fora do código.

- [ ] **Step 1: Escrever o runbook**

Criar `docs/ops/integracao-whoop.md` com:

**Configurar (uma vez):** criar o app em `developer.whoop.com` (imediato, sem aprovação, limite de 10 membros); registrar o Redirect URI `https://<dominio>/api/whoop/callback`; pegar Client ID e Secret; gerar a chave Fernet com `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`; colocar as três em `/opt/aath/.env` (chmod 600, nunca no git).

**Deploy:** `alembic upgrade head` para criar `whoop_connections`; rebuild da imagem do backend; recriar `api`, `worker` e `beat` (o beat precisa reiniciar para carregar o `beat_schedule` novo).

**As duas armadilhas:**
- O Redirect URI é amarrado ao domínio. Registrado com `62-171-128-103.sslip.io`, a troca para domínio próprio **exige reeditar o app no portal da Whoop** — o OAuth quebra silenciosamente com `redirect_uri` divergente.
- O limite de 10 membros é do app, não da conta do atleta. O 11º atleta recebe erro na troca de token, e a mensagem no card explica isso.

**O que cada estado significa:**

| Estado | Significado | Primeiro passo |
|---|---|---|
| `CONNECTED` sem `last_sync_at` recente | O beat não está rodando ou o token falha em silêncio | `docker logs aath_worker` filtrando por `whoop` |
| `NEEDS_REAUTH` | O atleta revogou o acesso no app da Whoop, ou o refresh token expirou | O atleta clica em Reconectar no `/importar` |
| Alerta de `task_failure` com `whoop_sync` | Falha real na integração | O corpo do email traz a exceção |

- [ ] **Step 2: Commit**

```bash
git add docs/ops/integracao-whoop.md
git commit -m "docs(ops): runbook da integracao Whoop"
```

---

## Verificação final (com evidência, não com fé)

- [ ] `bash <scratchpad>/vm-test.sh` — suíte do backend verde, colar a saída (esperado **559 passed**)
- [ ] `cd web && npx vitest run` — suíte do web verde
- [ ] **Sem as variáveis configuradas nada quebra:** `GET /api/v1/whoop/status` responde 503 e o card não aparece
- [ ] **Migração aplica e reverte:** `alembic upgrade head` e depois `alembic downgrade -1` sem erro
- [ ] **Conexão real:** conectar a Whoop de um atleta e confirmar `status=CONNECTED` com `connected_at` preenchido
- [ ] **Dado real no banco:** `select metric_date, hrv_ms, sleep_hours, source from recovery_metrics where source like '%whoop%' order by metric_date desc limit 5;` — a noite mais recente aparece com `source='whoop'`
- [ ] **Backfill:** confirmar ~180 dias de linhas e `backfilled_at` preenchido
- [ ] **Idempotência ao vivo:** rodar "sincronizar agora" duas vezes e confirmar que a segunda não altera nenhuma linha
- [ ] **Precedência ao vivo:** num dia que o Garmin já tinha alimentado, confirmar que o HRV passou a ser o da Whoop e que `source` virou `garmin+whoop`
- [ ] **O objetivo de tudo isso:** gerar uma recomendação e confirmar que a IA passou a usar HRV e sono, em vez de declarar "no sleep/HRV"

O último item é o único que importa de verdade. Os outros são o caminho até ele.
