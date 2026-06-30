# Garmin Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sincronismo bidirecional com Garmin Connect — importar atividades + wellness (Garmin→Hub) e empurrar/agendar treinos estruturados (Hub→Garmin) via a lib não-oficial `garminconnect`.

**Architecture:** A lib frágil é isolada atrás de uma interface fina (`GarminClient` Protocol) em `services/garmin/client.py` — único módulo que importa `garminconnect`. O `sync_service` recebe o client por injeção, então tudo é testado offline com um `FakeGarminClient`. Atividades reusam `ingestion_service.import_file`; wellness reusa `RecoveryMetric`. Token cifrado (Fernet) numa tabela `garmin_connections`. Sync roda via Celery (Beat diário + on-demand).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, Celery, Pydantic v2, `garminconnect>=0.3.6`, `cryptography` (Fernet), pytest/pytest-asyncio.

## Global Constraints

- Spec de referência: `docs/superpowers/specs/2026-06-30-garmin-sync-design.md`.
- Toda tabela athlete-scoped usa `Base` + `TenantMixin` (de `app/models/base.py`).
- Todo acesso a dado passa por repositório que herda `TenantRepository` (`app/repositories/base.py`) — isolamento por `athlete_id` é automático.
- `garminconnect` só pode ser importado dentro de `app/services/garmin/client.py`. Nenhum outro módulo o conhece; erros da lib são traduzidos para `GarminAuthError` / `GarminSyncError`.
- Senha do atleta **nunca** é persistida. Só o `token_dict` e o `client_state` do MFA, sempre cifrados via `token_store`.
- Testes não tocam rede nem a lib real: usam `FakeGarminClient`. A `RealGarminClient` (adapter de rede) não tem teste automatizado — é verificada manualmente no piloto.
- Datetimes sempre timezone-aware UTC (`datetime.now(timezone.utc)`).
- Versões mínimas (verbatim): `garminconnect>=0.3.6`, `cryptography>=42`.

---

### Task 1: Crypto boundary (`token_store`) + setting

**Files:**
- Modify: `backend/app/core/config.py:25-30` (adicionar setting na seção Security)
- Create: `backend/app/services/garmin/__init__.py`
- Create: `backend/app/services/garmin/token_store.py`
- Test: `backend/app/tests/test_garmin/__init__.py`, `backend/app/tests/test_garmin/test_token_store.py`

**Interfaces:**
- Consumes: `settings.garmin_token_key` (str Fernet key, base64).
- Produces:
  - `token_store.encrypt(data: dict) -> str`
  - `token_store.decrypt(blob: str) -> dict`
  - `token_store.is_enabled() -> bool` (True se `garmin_token_key` não-vazia)
  - `class GarminCryptoError(RuntimeError)`

- [ ] **Step 1: Write the failing test**

`backend/app/tests/test_garmin/__init__.py` → arquivo vazio.

`backend/app/tests/test_garmin/test_token_store.py`:
```python
"""token_store: round-trip de cifra Fernet do token/MFA-state do Garmin."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.services.garmin import token_store
from app.services.garmin.token_store import GarminCryptoError


def _key() -> str:
    return Fernet.generate_key().decode()


def test_round_trip_preserves_dict(monkeypatch):
    monkeypatch.setattr(token_store.settings, "garmin_token_key", _key())
    data = {"oauth1": {"token": "abc"}, "oauth2": {"access": "xyz", "expires": 123}}
    blob = token_store.encrypt(data)
    assert isinstance(blob, str)
    assert blob != str(data)  # ciphertext, não plaintext
    assert token_store.decrypt(blob) == data


def test_is_enabled_reflects_key(monkeypatch):
    monkeypatch.setattr(token_store.settings, "garmin_token_key", "")
    assert token_store.is_enabled() is False
    monkeypatch.setattr(token_store.settings, "garmin_token_key", _key())
    assert token_store.is_enabled() is True


def test_encrypt_without_key_raises(monkeypatch):
    monkeypatch.setattr(token_store.settings, "garmin_token_key", "")
    with pytest.raises(GarminCryptoError):
        token_store.encrypt({"a": 1})


def test_decrypt_garbage_raises(monkeypatch):
    monkeypatch.setattr(token_store.settings, "garmin_token_key", _key())
    with pytest.raises(GarminCryptoError):
        token_store.decrypt("not-a-valid-token")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_token_store.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.garmin.token_store`.

- [ ] **Step 3: Add the setting**

Em `backend/app/core/config.py`, dentro do bloco `# Security` (após `rate_limit_per_minute`, linha ~30):
```python
    # Garmin Connect (unofficial sync). Fernet key (base64) for token-at-rest.
    # Empty => feature disabled (routes return 503). Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    garmin_token_key: str = ""
```

- [ ] **Step 4: Implement `token_store.py`**

`backend/app/services/garmin/__init__.py` → arquivo vazio.

`backend/app/services/garmin/token_store.py`:
```python
"""Fernet encryption boundary for Garmin token + MFA client_state at rest.

The ONLY module that handles Garmin secret material's encryption. The athlete's
password is never stored; only the garth token_dict and the in-flight MFA
client_state pass through here, always encrypted with ``settings.garmin_token_key``.
"""
from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class GarminCryptoError(RuntimeError):
    """Raised when encryption/decryption fails or the key is missing."""


def is_enabled() -> bool:
    return bool(settings.garmin_token_key)


def _fernet() -> Fernet:
    if not settings.garmin_token_key:
        raise GarminCryptoError("garmin_token_key is not configured")
    try:
        return Fernet(settings.garmin_token_key.encode())
    except (ValueError, TypeError) as exc:
        raise GarminCryptoError(f"invalid garmin_token_key: {exc}") from exc


def encrypt(data: dict) -> str:
    f = _fernet()
    return f.encrypt(json.dumps(data).encode()).decode()


def decrypt(blob: str) -> dict:
    f = _fernet()
    try:
        return json.loads(f.decrypt(blob.encode()).decode())
    except (InvalidToken, ValueError) as exc:
        raise GarminCryptoError(f"could not decrypt token: {exc}") from exc
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_token_store.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/app/services/garmin/ backend/app/tests/test_garmin/
git commit -m "feat(garmin): token_store Fernet crypto boundary + setting"
```

---

### Task 2: `GarminConnection` model, enum e migration

**Files:**
- Modify: `backend/app/models/enums.py` (adicionar `GarminConnectionStatus`)
- Create: `backend/app/models/garmin.py`
- Modify: `backend/app/models/__init__.py` (registrar o model)
- Create: `backend/alembic/versions/0009_garmin_connection.py`
- Test: `backend/app/tests/test_garmin/test_model.py`

**Interfaces:**
- Consumes: `Base`, `TenantMixin` (`app/models/base.py`).
- Produces:
  - `GarminConnectionStatus` enum: `AWAITING_MFA`, `CONNECTED`, `NEEDS_REAUTH`, `DISCONNECTED` (valores string iguais ao nome).
  - `GarminConnection` model com colunas: `status: GarminConnectionStatus`, `encrypted_token: str|None`, `mfa_state: str|None`, `mfa_expires_at: datetime|None`, `last_sync_at: datetime|None`, `last_error: str|None`, `connected_at: datetime|None`. Tabela `garmin_connections`, `athlete_id` UNIQUE.

- [ ] **Step 1: Write the failing test**

`backend/app/tests/test_garmin/test_model.py`:
```python
"""GarminConnection persiste e é athlete-scoped."""
from __future__ import annotations

import pytest

from app.models.enums import GarminConnectionStatus
from app.models.garmin import GarminConnection


@pytest.mark.asyncio
async def test_persist_and_read(session, two_athletes):
    a, _ = two_athletes
    conn = GarminConnection(
        athlete_id=a.id, status=GarminConnectionStatus.CONNECTED,
        encrypted_token="cipher",
    )
    session.add(conn)
    await session.flush()
    assert conn.id is not None
    assert conn.status is GarminConnectionStatus.CONNECTED
    assert conn.created_at is not None  # vem do Base
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: app.models.garmin`.

- [ ] **Step 3: Add the enum**

Em `backend/app/models/enums.py`, no fim do arquivo:
```python
class GarminConnectionStatus(str, enum.Enum):
    AWAITING_MFA = "AWAITING_MFA"
    CONNECTED = "CONNECTED"
    NEEDS_REAUTH = "NEEDS_REAUTH"
    DISCONNECTED = "DISCONNECTED"
```

- [ ] **Step 4: Create the model**

`backend/app/models/garmin.py`:
```python
"""Garmin Connect link: one row per athlete. Holds the encrypted garth token
(never the password) and the connection lifecycle status."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin
from app.models.enums import GarminConnectionStatus


class GarminConnection(Base, TenantMixin):
    __tablename__ = "garmin_connections"
    __table_args__ = (
        UniqueConstraint("athlete_id", name="uq_garmin_conn_athlete"),
    )

    status: Mapped[GarminConnectionStatus] = mapped_column(
        Enum(GarminConnectionStatus, native_enum=False, length=32),
        default=GarminConnectionStatus.DISCONNECTED,
        nullable=False,
    )
    encrypted_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 5: Register the model**

Em `backend/app/models/__init__.py`, após a linha de import de `audit`:
```python
from app.models.garmin import GarminConnection
```
E adicionar `"GarminConnection",` ao `__all__`.

- [ ] **Step 6: Run the model test (passes via SQLite metadata)**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_model.py -v`
Expected: PASS (1 passed). (O conftest cria todas as tabelas de `Base.metadata` no SQLite; nenhuma migration necessária para o teste.)

- [ ] **Step 7: Write the Alembic migration**

`backend/alembic/versions/0009_garmin_connection.py`:
```python
"""garmin_connections table

Revision ID: 0009
Revises: 0008
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "garmin_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("athlete_id", UUID(as_uuid=True), sa.ForeignKey("athletes.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DISCONNECTED"),
        sa.Column("encrypted_token", sa.Text(), nullable=True),
        sa.Column("mfa_state", sa.Text(), nullable=True),
        sa.Column("mfa_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_garmin_conn_athlete", "garmin_connections", ["athlete_id"])
    op.create_unique_constraint("uq_garmin_conn_athlete", "garmin_connections", ["athlete_id"])


def downgrade() -> None:
    op.drop_constraint("uq_garmin_conn_athlete", "garmin_connections", type_="unique")
    op.drop_index("ix_garmin_conn_athlete", table_name="garmin_connections")
    op.drop_table("garmin_connections")
```

- [ ] **Step 8: Verify the migration applies (against a running Postgres)**

Run: `cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
Expected: sem erro; a tabela `garmin_connections` é criada/derrubada/recriada. (Requer Postgres do `docker-compose` no ar. Se indisponível, marcar como verificação manual e seguir — os testes usam SQLite.)

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/ backend/alembic/versions/0009_garmin_connection.py backend/app/tests/test_garmin/test_model.py
git commit -m "feat(garmin): GarminConnection model, status enum, migration 0009"
```

---

### Task 3: `GarminConnectionRepository`

**Files:**
- Create: `backend/app/repositories/garmin_repo.py`
- Test: `backend/app/tests/test_garmin/test_repo.py`

**Interfaces:**
- Consumes: `TenantRepository`, `GarminConnection`, `GarminConnectionStatus`.
- Produces:
  - `class GarminConnectionRepository(TenantRepository[GarminConnection])`
  - `async get_for_athlete(athlete_id=None) -> GarminConnection | None` (a única conexão do tenant)
  - `async get_or_create(athlete_id=None) -> GarminConnection`

- [ ] **Step 1: Write the failing test**

`backend/app/tests/test_garmin/test_repo.py`:
```python
"""Repositório da conexão Garmin: 1 por atleta, isolado por tenant."""
from __future__ import annotations

import pytest

from app.models.enums import GarminConnectionStatus
from app.repositories.garmin_repo import GarminConnectionRepository
from app.tests.conftest import ctx_for


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent(session, two_athletes):
    a, _ = two_athletes
    repo = GarminConnectionRepository(session, ctx_for(a))
    c1 = await repo.get_or_create()
    c2 = await repo.get_or_create()
    assert c1.id == c2.id
    assert c1.status is GarminConnectionStatus.DISCONNECTED


@pytest.mark.asyncio
async def test_tenant_isolation(session, two_athletes):
    a, b = two_athletes
    repo_a = GarminConnectionRepository(session, ctx_for(a))
    await repo_a.get_or_create()
    repo_b = GarminConnectionRepository(session, ctx_for(b))
    assert await repo_b.get_for_athlete() is None  # B não vê a conexão de A
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: app.repositories.garmin_repo`.

- [ ] **Step 3: Implement the repository**

`backend/app/repositories/garmin_repo.py`:
```python
"""Repository for the single Garmin connection per athlete."""
from __future__ import annotations

import uuid

from app.models.garmin import GarminConnection
from app.repositories.base import TenantRepository


class GarminConnectionRepository(TenantRepository[GarminConnection]):
    model = GarminConnection

    async def get_for_athlete(
        self, athlete_id: uuid.UUID | None = None
    ) -> GarminConnection | None:
        stmt = self._base_select(athlete_id).limit(1)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_or_create(
        self, athlete_id: uuid.UUID | None = None
    ) -> GarminConnection:
        existing = await self.get_for_athlete(athlete_id)
        if existing:
            return existing
        conn = GarminConnection(athlete_id=self._scoped_athlete_id(athlete_id))
        return await self.add(conn)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_repo.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/garmin_repo.py backend/app/tests/test_garmin/test_repo.py
git commit -m "feat(garmin): GarminConnectionRepository (get_or_create, tenant-scoped)"
```

---

### Task 4: Client Protocol, tipos de dados, exceções e `FakeGarminClient`

**Files:**
- Create: `backend/app/services/garmin/types.py`
- Create: `backend/app/services/garmin/client.py` (Protocol + exceções; `RealGarminClient` vem na Task 5)
- Create: `backend/app/services/garmin/fake_client.py`
- Test: `backend/app/tests/test_garmin/test_fake_client.py`

**Interfaces:**
- Produces:
  - `types.ActivityRef`: `activity_id: str`, `start_time: datetime`, `name: str | None`.
  - `types.WellnessSnapshot`: `day: date`, `hrv_ms: float | None`, `resting_hr: int | None`, `sleep_hours: float | None`, `sleep_score: float | None`, `body_battery: float | None`.
  - `types.Connected(token: dict)`, `types.NeedsMfa(client_state: dict)`, `LoginResult = Connected | NeedsMfa`.
  - `client.GarminClient` (Protocol) com os métodos do spec §4.1.
  - `client.GarminAuthError`, `client.GarminSyncError`.
  - `fake_client.FakeGarminClient(...)` configurável para testes.

- [ ] **Step 1: Write the failing test**

`backend/app/tests/test_garmin/test_fake_client.py`:
```python
"""FakeGarminClient honra o Protocol e devolve dados configurados."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.services.garmin.client import GarminAuthError
from app.services.garmin.fake_client import FakeGarminClient
from app.services.garmin.types import Connected, NeedsMfa, WellnessSnapshot


def test_login_needs_mfa_then_resume():
    fc = FakeGarminClient(needs_mfa=True)
    res = fc.login("e@x.com", "pw")
    assert isinstance(res, NeedsMfa)
    token = fc.resume_mfa(res.client_state, "123456")
    assert token == {"fake": "token"}


def test_login_direct_when_no_mfa():
    fc = FakeGarminClient(needs_mfa=False)
    res = fc.login("e@x.com", "pw")
    assert isinstance(res, Connected)
    assert res.token == {"fake": "token"}


def test_list_and_download_activity():
    act = WellnessSnapshot(day=date(2026, 6, 30), hrv_ms=60.0, resting_hr=48,
                           sleep_hours=7.5, sleep_score=80.0, body_battery=70.0)
    fc = FakeGarminClient(
        activities=[("act-1", datetime(2026, 6, 30, 6, tzinfo=timezone.utc))],
        fit_bytes=b"FIT-BYTES", wellness={date(2026, 6, 30): act},
    )
    fc.resume({"fake": "token"})
    refs = fc.list_activities(date(2026, 6, 1))
    assert refs[0].activity_id == "act-1"
    assert fc.download_activity_fit("act-1") == b"FIT-BYTES"
    assert fc.get_wellness(date(2026, 6, 30)).hrv_ms == 60.0


def test_auth_error_is_raisable():
    fc = FakeGarminClient(raise_auth_on_resume=True)
    try:
        fc.resume({"fake": "token"})
        assert False, "expected GarminAuthError"
    except GarminAuthError:
        pass


def test_push_and_unschedule_record_calls():
    fc = FakeGarminClient()
    fc.resume({"fake": "token"})
    wid = fc.push_workout({"name": "W"}, date(2026, 7, 1))
    assert wid == "garmin-workout-1"
    assert fc.pushed[0] == ({"name": "W"}, date(2026, 7, 1))
    fc.unschedule_workout(wid)
    assert wid in fc.unscheduled
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_fake_client.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.garmin.types`.

- [ ] **Step 3: Implement `types.py`**

`backend/app/services/garmin/types.py`:
```python
"""Plain data types crossing the Garmin client boundary (no lib imports)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class ActivityRef:
    activity_id: str
    start_time: datetime
    name: str | None = None


@dataclass(frozen=True)
class WellnessSnapshot:
    day: date
    hrv_ms: float | None = None
    resting_hr: int | None = None
    sleep_hours: float | None = None
    sleep_score: float | None = None
    body_battery: float | None = None


@dataclass(frozen=True)
class Connected:
    token: dict


@dataclass(frozen=True)
class NeedsMfa:
    client_state: dict


LoginResult = Connected | NeedsMfa
```

- [ ] **Step 4: Implement `client.py` (Protocol + exceções)**

`backend/app/services/garmin/client.py`:
```python
"""Garmin client interface. The concrete RealGarminClient (Task 5) is the ONLY
place that imports ``garminconnect``. Everything else depends on this Protocol,
so the whole system is testable offline with FakeGarminClient."""
from __future__ import annotations

from datetime import date
from typing import Protocol

from app.services.garmin.types import ActivityRef, LoginResult, WellnessSnapshot


class GarminAuthError(RuntimeError):
    """Auth failed / token invalid (maps to needs_reauth)."""


class GarminSyncError(RuntimeError):
    """A non-auth Garmin call failed (network, parse, rate-limit)."""


class GarminClient(Protocol):
    def login(self, email: str, password: str) -> LoginResult: ...
    def resume_mfa(self, client_state: dict, mfa_code: str) -> dict: ...
    def resume(self, token: dict) -> None: ...
    def list_activities(self, since: date) -> list[ActivityRef]: ...
    def download_activity_fit(self, activity_id: str) -> bytes: ...
    def get_wellness(self, day: date) -> WellnessSnapshot: ...
    def push_workout(self, structured_workout: dict, schedule_date: date) -> str: ...
    def unschedule_workout(self, garmin_workout_id: str) -> None: ...
    def current_token(self) -> dict | None: ...
```

- [ ] **Step 5: Implement `fake_client.py`**

`backend/app/services/garmin/fake_client.py`:
```python
"""In-memory GarminClient for tests. No network, no garminconnect import."""
from __future__ import annotations

from datetime import date, datetime

from app.services.garmin.client import GarminAuthError
from app.services.garmin.types import (
    ActivityRef,
    Connected,
    LoginResult,
    NeedsMfa,
    WellnessSnapshot,
)


class FakeGarminClient:
    def __init__(
        self,
        *,
        needs_mfa: bool = False,
        activities: list[tuple[str, datetime]] | None = None,
        fit_bytes: bytes = b"FIT",
        wellness: dict[date, WellnessSnapshot] | None = None,
        raise_auth_on_resume: bool = False,
    ):
        self._needs_mfa = needs_mfa
        self._activities = activities or []
        self._fit_bytes = fit_bytes
        self._wellness = wellness or {}
        self._raise_auth_on_resume = raise_auth_on_resume
        self._token: dict | None = None
        self.pushed: list[tuple[dict, date]] = []
        self.unscheduled: list[str] = []
        self._workout_seq = 0

    def login(self, email: str, password: str) -> LoginResult:
        if self._needs_mfa:
            return NeedsMfa(client_state={"stage": "mfa", "email": email})
        return Connected(token={"fake": "token"})

    def resume_mfa(self, client_state: dict, mfa_code: str) -> dict:
        return {"fake": "token"}

    def resume(self, token: dict) -> None:
        if self._raise_auth_on_resume:
            raise GarminAuthError("token expired")
        self._token = token

    def list_activities(self, since: date) -> list[ActivityRef]:
        return [
            ActivityRef(activity_id=aid, start_time=ts)
            for aid, ts in self._activities
            if ts.date() >= since
        ]

    def download_activity_fit(self, activity_id: str) -> bytes:
        return self._fit_bytes

    def get_wellness(self, day: date) -> WellnessSnapshot:
        return self._wellness.get(day, WellnessSnapshot(day=day))

    def push_workout(self, structured_workout: dict, schedule_date: date) -> str:
        self._workout_seq += 1
        wid = f"garmin-workout-{self._workout_seq}"
        self.pushed.append((structured_workout, schedule_date))
        return wid

    def unschedule_workout(self, garmin_workout_id: str) -> None:
        self.unscheduled.append(garmin_workout_id)

    def current_token(self) -> dict | None:
        return self._token
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_fake_client.py -v`
Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/garmin/types.py backend/app/services/garmin/client.py backend/app/services/garmin/fake_client.py backend/app/tests/test_garmin/test_fake_client.py
git commit -m "feat(garmin): client Protocol, boundary types, FakeGarminClient"
```

---

### Task 5: `RealGarminClient` (adapter da lib — sem teste automatizado)

**Files:**
- Modify: `backend/app/services/garmin/client.py` (adicionar `RealGarminClient`)

**Interfaces:**
- Consumes: `garminconnect` (Garmin, exceções), `types.*`.
- Produces: `RealGarminClient` implementando `GarminClient`.

> **NOTA DE VERIFICAÇÃO:** os nomes exatos de métodos do `garminconnect` 0.3.6 (`Garmin(...)`, `login(return_on_mfa=True)`, `get_activities`, `download_activity`, `get_rhr_day`/`get_hrv_data`/`get_sleep_data`/`get_body_battery`, criação de workout) DEVEM ser conferidos contra a versão instalada antes/durante a implementação (ver disclaimer do spec). O esqueleto abaixo reflete a API conhecida em 2026-06; ajuste os nomes se a lib divergir. Como toca rede/credenciais, **não há teste automatizado** — validação é manual no piloto (Task 10 / gate do spec §7).

- [ ] **Step 1: Implement `RealGarminClient`**

Adicionar ao final de `backend/app/services/garmin/client.py`:
```python
# --- Concrete adapter (the ONLY garminconnect import in the codebase) --------
from datetime import datetime, timezone  # noqa: E402

from app.services.garmin.types import (  # noqa: E402
    ActivityRef,
    Connected,
    NeedsMfa,
    WellnessSnapshot,
)


class RealGarminClient:
    """Adapter over python-garminconnect. Translates lib errors to
    GarminAuthError / GarminSyncError so callers never see lib exceptions."""

    def __init__(self) -> None:
        self._api = None  # garminconnect.Garmin instance, set on login/resume

    def login(self, email: str, password: str):
        from garminconnect import Garmin
        from garminconnect import GarminConnectAuthenticationError

        self._api = Garmin(email=email, password=password, return_on_mfa=True)
        try:
            result1, client_state = self._api.login()
        except GarminConnectAuthenticationError as exc:
            raise GarminAuthError(str(exc)) from exc
        if result1 == "needs_mfa":
            return NeedsMfa(client_state=client_state)
        return Connected(token=self._dump_token())

    def resume_mfa(self, client_state: dict, mfa_code: str) -> dict:
        from garminconnect import GarminConnectAuthenticationError

        if self._api is None:
            from garminconnect import Garmin

            self._api = Garmin(return_on_mfa=True)
        try:
            self._api.resume_login(client_state, mfa_code)
        except GarminConnectAuthenticationError as exc:
            raise GarminAuthError(str(exc)) from exc
        return self._dump_token()

    def resume(self, token: dict) -> None:
        from garminconnect import Garmin
        from garminconnect import GarminConnectAuthenticationError

        self._api = Garmin()
        try:
            self._api.garth.loads(token)  # restore serialized garth session
            self._api.garth.refresh_oauth2()  # force-refresh; raises if invalid
        except Exception as exc:  # noqa: BLE001 — any restore failure => reauth
            raise GarminAuthError(f"token restore failed: {exc}") from exc

    def _dump_token(self) -> dict:
        return self._api.garth.dumps()

    def current_token(self) -> dict | None:
        return self._dump_token() if self._api else None

    def list_activities(self, since):
        try:
            raw = self._api.get_activities_by_date(since.isoformat(),
                                                   datetime.now(timezone.utc).date().isoformat())
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"list_activities failed: {exc}") from exc
        out = []
        for a in raw:
            ts = datetime.fromisoformat(a["startTimeGMT"].replace(" ", "T")).replace(
                tzinfo=timezone.utc
            )
            out.append(ActivityRef(activity_id=str(a["activityId"]), start_time=ts,
                                    name=a.get("activityName")))
        return out

    def download_activity_fit(self, activity_id: str) -> bytes:
        from garminconnect import Garmin

        try:
            return self._api.download_activity(
                activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
            )
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"download failed: {exc}") from exc

    def get_wellness(self, day) -> WellnessSnapshot:
        iso = day.isoformat()
        try:
            hrv = self._api.get_hrv_data(iso) or {}
            sleep = self._api.get_sleep_data(iso) or {}
            rhr = self._api.get_rhr_day(iso) or {}
            bb = self._api.get_body_battery(iso, iso) or []
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"wellness fetch failed: {exc}") from exc
        daily_sleep = sleep.get("dailySleepDTO", {}) if isinstance(sleep, dict) else {}
        sleep_secs = daily_sleep.get("sleepTimeSeconds")
        bb_charged = None
        if bb and isinstance(bb, list):
            charged = [d.get("charged") for d in bb if isinstance(d, dict)]
            bb_charged = max([c for c in charged if c is not None], default=None)
        return WellnessSnapshot(
            day=day,
            hrv_ms=(hrv.get("hrvSummary") or {}).get("lastNightAvg"),
            resting_hr=(rhr.get("allMetrics", {}).get("metricsMap", {})
                        .get("WELLNESS_RESTING_HEART_RATE", [{}])[0].get("value")
                        if rhr else None),
            sleep_hours=(sleep_secs / 3600.0) if sleep_secs else None,
            sleep_score=(daily_sleep.get("sleepScores", {}).get("overall", {})
                         .get("value")),
            body_battery=bb_charged,
        )

    def push_workout(self, structured_workout: dict, schedule_date) -> str:
        try:
            created = self._api.upload_workout(structured_workout)
            workout_id = str(created.get("workoutId"))
            self._api.schedule_workout(workout_id, schedule_date.isoformat())
            return workout_id
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"push_workout failed: {exc}") from exc

    def unschedule_workout(self, garmin_workout_id: str) -> None:
        try:
            self._api.delete_workout(garmin_workout_id)
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"unschedule failed: {exc}") from exc
```

- [ ] **Step 2: Verify it imports without a broker/network**

Run: `cd backend && python -c "from app.services.garmin.client import RealGarminClient; RealGarminClient()"`
Expected: sem erro (a importação de `garminconnect` é lazy dentro dos métodos; instanciar não conecta). Se `garminconnect` ainda não estiver instalado, esta verificação fica para depois da Task 10 (deps) — nesse caso confirmar só que o módulo `client.py` importa.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/garmin/client.py
git commit -m "feat(garmin): RealGarminClient adapter over garminconnect (lazy import)"
```

---

### Task 6: Tradutor `StructuredWorkout` → dict de workout do Garmin

**Files:**
- Create: `backend/app/services/garmin/workout_translator.py`
- Test: `backend/app/tests/test_garmin/test_workout_translator.py`

**Interfaces:**
- Consumes: `app.services.workout.model.StructuredWorkout, Step, Repeat, Target`.
- Produces: `workout_translator.to_garmin_workout(sw: StructuredWorkout) -> dict` — dict no formato que `RealGarminClient.push_workout` envia (estrutura de workout do Garmin: `workoutName`, `sportType=cycling`, `workoutSegments[0].workoutSteps[]`). Targets de potência em **watts absolutos** (resolvidos via `sw.ftp_watts`), porque a API de workout do Garmin usa watts, não %FTP.

- [ ] **Step 1: Write the failing test**

`backend/app/tests/test_garmin/test_workout_translator.py`:
```python
"""Tradução do modelo canônico para o dict de workout do Garmin."""
from __future__ import annotations

from app.services.garmin.workout_translator import to_garmin_workout
from app.services.workout.model import Repeat, Step, StructuredWorkout, Target


def _sw() -> StructuredWorkout:
    return StructuredWorkout(
        name="VO2 4x4",
        ftp_watts=250.0,
        elements=[
            Step(intensity="warmup", duration_s=600,
                 target=Target(type="power_pct_ftp", low=0.5, high=0.7)),
            Repeat(count=4, steps=[
                Step(intensity="active", duration_s=240,
                     target=Target(type="power_pct_ftp", low=1.1, high=1.2)),
                Step(intensity="rest", duration_s=240,
                     target=Target(type="power_pct_ftp", low=0.5, high=0.5)),
            ]),
            Step(intensity="cooldown", duration_s=300, target=Target(type="open")),
        ],
    )


def test_basic_shape():
    g = to_garmin_workout(_sw())
    assert g["workoutName"] == "VO2 4x4"
    assert g["sportType"]["sportTypeKey"] == "cycling"
    steps = g["workoutSegments"][0]["workoutSteps"]
    # warmup + repeat-group + cooldown = 3 top-level steps
    assert len(steps) == 3


def test_power_resolved_to_watts():
    g = to_garmin_workout(_sw())
    steps = g["workoutSegments"][0]["workoutSteps"]
    warmup = steps[0]
    # 0.5..0.7 * 250 = 125..175 W
    assert warmup["targetValueOne"] == 125
    assert warmup["targetValueTwo"] == 175


def test_repeat_group_has_children():
    g = to_garmin_workout(_sw())
    repeat = g["workoutSegments"][0]["workoutSteps"][1]
    assert repeat["type"] == "RepeatGroupDTO"
    assert repeat["numberOfIterations"] == 4
    assert len(repeat["workoutSteps"]) == 2


def test_open_target_has_no_power():
    g = to_garmin_workout(_sw())
    cooldown = g["workoutSegments"][0]["workoutSteps"][2]
    assert cooldown.get("targetType", {}).get("workoutTargetTypeKey") == "no.target"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_workout_translator.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.garmin.workout_translator`.

- [ ] **Step 3: Implement the translator**

`backend/app/services/garmin/workout_translator.py`:
```python
"""Translate the canonical StructuredWorkout into Garmin Connect's workout dict.

Garmin's workout API expects absolute watts, so %FTP fractions are resolved via
``sw.ftp_watts``. Repeats map to a RepeatGroupDTO (no flattening). This dict is
what RealGarminClient.push_workout uploads."""
from __future__ import annotations

from app.services.workout.model import Repeat, Step, StructuredWorkout, Target

_INTENSITY_KEY = {
    "warmup": "warmup",
    "active": "interval",
    "rest": "recovery",
    "cooldown": "cooldown",
}


def _watts(target: Target, ftp: float | None) -> tuple[int | None, int | None]:
    if target.type != "power_pct_ftp" or target.low is None or ftp is None:
        return None, None
    high = target.high if target.high is not None else target.low
    return round(target.low * ftp), round(high * ftp)


def _step_dto(step: Step, ftp: float | None, order: int) -> dict:
    low, high = _watts(step.target, ftp)
    dto: dict = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeKey": _INTENSITY_KEY[step.intensity]},
        "endCondition": {"conditionTypeKey": "time"},
        "endConditionValue": step.duration_s,
    }
    if low is None:
        dto["targetType"] = {"workoutTargetTypeKey": "no.target"}
    else:
        dto["targetType"] = {"workoutTargetTypeKey": "power.zone"}
        dto["targetValueOne"] = low
        dto["targetValueTwo"] = high
    return dto


def to_garmin_workout(sw: StructuredWorkout) -> dict:
    ftp = sw.ftp_watts
    steps: list[dict] = []
    order = 1
    for el in sw.elements:
        if isinstance(el, Repeat):
            children = []
            for child in el.steps:
                children.append(_step_dto(child, ftp, order))
                order += 1
            steps.append({
                "type": "RepeatGroupDTO",
                "stepType": {"stepTypeKey": "repeat"},
                "numberOfIterations": el.count,
                "workoutSteps": children,
            })
        else:  # Step
            steps.append(_step_dto(el, ftp, order))
            order += 1
    return {
        "workoutName": sw.name,
        "sportType": {"sportTypeKey": "cycling"},
        "workoutSegments": [
            {"segmentOrder": 1,
             "sportType": {"sportTypeKey": "cycling"},
             "workoutSteps": steps},
        ],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_workout_translator.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/garmin/workout_translator.py backend/app/tests/test_garmin/test_workout_translator.py
git commit -m "feat(garmin): StructuredWorkout -> Garmin workout dict translator"
```

---

### Task 7: `sync_service.pull` (atividades + wellness, idempotente)

**Files:**
- Create: `backend/app/services/garmin/sync_service.py`
- Test: `backend/app/tests/test_garmin/test_sync_pull.py`

**Interfaces:**
- Consumes: `GarminClient`, `GarminConnectionRepository`, `ingestion_service.import_file`, `RecoveryRepository`, `RecoveryMetric`, `token_store`, `GarminAuthError`.
- Produces:
  - `dataclass PullResult(activities_imported: int, duplicates: int, wellness_days: int)`
  - `async sync_pull(session, ctx, client: GarminClient, athlete_id) -> PullResult`
  - Em `GarminAuthError`: marca a conexão `NEEDS_REAUTH`, grava `last_error`, re-levanta? Não — retorna após marcar (a task trata). Definir: **levanta `GarminAuthError`** após marcar, para o job logar; o teste verifica o status persistido.

- [ ] **Step 1: Write the failing test**

`backend/app/tests/test_garmin/test_sync_pull.py`:
```python
"""sync_pull: importa atividades via pipeline real + upsert de wellness; idempotente."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.enums import GarminConnectionStatus
from app.repositories.garmin_repo import GarminConnectionRepository
from app.repositories.metrics_repo import RecoveryRepository
from app.repositories.workout_repo import WorkoutRepository
from app.services.garmin.fake_client import FakeGarminClient
from app.services.garmin.sync_service import sync_pull
from app.services.garmin.client import GarminAuthError
from app.services.garmin.types import WellnessSnapshot
from app.tests.conftest import ctx_for

# Um FIT mínimo válido é difícil de forjar inline; usamos um CSV de 1 atividade,
# que a pipeline aceita. O FakeGarminClient devolve esses bytes e o sync chama
# import_file com filename ".csv" quando source-format é csv (ver nota no service).
_CSV = (
    b"date,duration_s,distance_m,avg_power,external_id\n"
    b"2026-06-30T06:00:00,3600,30000,200,garmin-act-1\n"
)


def _client():
    snap = WellnessSnapshot(day=date(2026, 6, 30), hrv_ms=62.0, resting_hr=47,
                            sleep_hours=7.0, sleep_score=78.0, body_battery=66.0)
    return FakeGarminClient(
        activities=[("garmin-act-1", datetime(2026, 6, 30, 6, tzinfo=timezone.utc))],
        fit_bytes=_CSV, wellness={date(2026, 6, 30): snap},
    )


@pytest.mark.asyncio
async def test_pull_imports_activity_and_wellness(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    await GarminConnectionRepository(session, ctx).get_or_create()
    res = await sync_pull(session, ctx, _client(), a.id)
    assert res.activities_imported == 1
    assert res.wellness_days == 1
    rec = await RecoveryRepository(session, ctx).list_recent(date(2026, 6, 1))
    assert rec[0].hrv_ms == 62.0
    assert rec[0].source == "garmin"


@pytest.mark.asyncio
async def test_pull_is_idempotent(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    await GarminConnectionRepository(session, ctx).get_or_create()
    await sync_pull(session, ctx, _client(), a.id)
    res2 = await sync_pull(session, ctx, _client(), a.id)
    assert res2.duplicates == 1
    assert res2.activities_imported == 0
    workouts = await WorkoutRepository(session, ctx).list()
    assert len(workouts) == 1  # não duplicou


@pytest.mark.asyncio
async def test_auth_error_marks_needs_reauth(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    await GarminConnectionRepository(session, ctx).get_or_create()
    bad = FakeGarminClient(raise_auth_on_resume=True)
    with pytest.raises(GarminAuthError):
        await sync_pull(session, ctx, bad, a.id)
    conn = await GarminConnectionRepository(session, ctx).get_for_athlete()
    assert conn.status is GarminConnectionStatus.NEEDS_REAUTH
    assert conn.last_error
```

> Nota: o teste usa CSV como "fit_bytes" porque forjar um FIT binário inline é frágil. O `sync_service` decide o filename pela extensão lógica; para manter a pipeline real, o service usa `filename=f"{activity_id}.fit"` em produção, mas aceita um override de extensão por parâmetro `_activity_ext` (default `"fit"`) usado só no teste. Ver Step 3.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_sync_pull.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.garmin.sync_service`.

- [ ] **Step 3: Implement `sync_pull`**

`backend/app/services/garmin/sync_service.py`:
```python
"""Orchestrates Garmin pull/push. Receives the GarminClient by injection so the
whole flow is testable offline. Reuses ingestion_service for activities and
RecoveryMetric for wellness."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.models.enums import GarminConnectionStatus
from app.models.metrics import RecoveryMetric
from app.repositories.garmin_repo import GarminConnectionRepository
from app.repositories.metrics_repo import RecoveryRepository
from app.services.garmin import token_store
from app.services.garmin.client import GarminAuthError, GarminClient
from app.services.ingestion.ingestion_service import import_file

log = get_logger(__name__)

_PULL_MARGIN_DAYS = 2


@dataclass
class PullResult:
    activities_imported: int
    duplicates: int
    wellness_days: int


async def _mark_reauth(repo, conn, message: str) -> None:
    conn.status = GarminConnectionStatus.NEEDS_REAUTH
    conn.last_error = message[:512]
    await repo.session.flush()


def _since(conn) -> date:
    base = conn.last_sync_at.date() if conn.last_sync_at else date(2020, 1, 1)
    return base - timedelta(days=_PULL_MARGIN_DAYS)


async def sync_pull(
    session: AsyncSession,
    ctx: TenantContext,
    client: GarminClient,
    athlete_id: uuid.UUID,
    *,
    _activity_ext: str = "fit",
) -> PullResult:
    conn_repo = GarminConnectionRepository(session, ctx)
    conn = await conn_repo.get_or_create(athlete_id)
    rec_repo = RecoveryRepository(session, ctx)

    if not conn.encrypted_token and conn.status is not GarminConnectionStatus.DISCONNECTED:
        pass  # tests may not set a token; resume() drives auth

    try:
        token = token_store.decrypt(conn.encrypted_token) if conn.encrypted_token else {}
        client.resume(token)
    except GarminAuthError as exc:
        await _mark_reauth(conn_repo, conn, str(exc))
        raise

    since = _since(conn)

    imported = 0
    duplicates = 0
    try:
        for ref in client.list_activities(since):
            data = client.download_activity_fit(ref.activity_id)
            result = await import_file(
                session, ctx, athlete_id,
                filename=f"{ref.activity_id}.{_activity_ext}",
                data=data, source="garmin",
            )
            imported += result.workouts_created
            duplicates += result.duplicates_skipped
    except GarminAuthError as exc:
        await _mark_reauth(conn_repo, conn, str(exc))
        raise

    wellness_days = 0
    day = since
    today = datetime.now(timezone.utc).date()
    while day <= today:
        snap = client.get_wellness(day)
        if any([snap.hrv_ms, snap.resting_hr, snap.sleep_hours,
                snap.sleep_score, snap.body_battery]):
            existing = await rec_repo.get_for_date(day, athlete_id)
            if existing is None:
                existing = RecoveryMetric(athlete_id=athlete_id, metric_date=day)
                await rec_repo.add(existing)
            existing.hrv_ms = snap.hrv_ms
            existing.resting_hr = snap.resting_hr
            existing.sleep_hours = snap.sleep_hours
            existing.sleep_score = snap.sleep_score
            existing.recovery_score = snap.body_battery
            existing.source = "garmin"
            wellness_days += 1
        day += timedelta(days=1)

    new_token = client.current_token()
    if new_token and token_store.is_enabled():
        conn.encrypted_token = token_store.encrypt(new_token)
    conn.status = GarminConnectionStatus.CONNECTED
    conn.last_sync_at = datetime.now(timezone.utc)
    conn.last_error = None
    await session.flush()

    return PullResult(imported, duplicates, wellness_days)
```

- [ ] **Step 4: Add `get_for_date` to `RecoveryRepository`**

Em `backend/app/repositories/metrics_repo.py`, dentro de `RecoveryRepository`:
```python
    async def get_for_date(
        self, d: date, athlete_id: uuid.UUID | None = None
    ) -> RecoveryMetric | None:
        stmt = self._base_select(athlete_id).where(RecoveryMetric.metric_date == d)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_sync_pull.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Run the whole garmin suite (no regressions)**

Run: `cd backend && python -m pytest app/tests/test_garmin/ -v`
Expected: todos passam.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/garmin/sync_service.py backend/app/repositories/metrics_repo.py backend/app/tests/test_garmin/test_sync_pull.py
git commit -m "feat(garmin): sync_pull (activities via ingestion + wellness upsert, idempotent)"
```

---

### Task 8: `sync_service.push` (traduz, envia, guarda id; unschedule no revert)

**Files:**
- Modify: `backend/app/services/garmin/sync_service.py` (adicionar `sync_push`, `sync_unpush`)
- Test: `backend/app/tests/test_garmin/test_sync_push.py`

**Interfaces:**
- Consumes: `workout_translator.to_garmin_workout`, `StructuredWorkout`, `GarminClient`.
- Produces:
  - `async sync_push(session, ctx, client, athlete_id, sw: StructuredWorkout, schedule_date: date) -> str` (retorna `garmin_workout_id`).
  - `async sync_unpush(session, ctx, client, garmin_workout_id: str) -> None`.

- [ ] **Step 1: Write the failing test**

`backend/app/tests/test_garmin/test_sync_push.py`:
```python
"""sync_push traduz e envia; sync_unpush remove o agendamento."""
from __future__ import annotations

from datetime import date

import pytest

from app.repositories.garmin_repo import GarminConnectionRepository
from app.services.garmin.fake_client import FakeGarminClient
from app.services.garmin.sync_service import sync_push, sync_unpush
from app.services.workout.model import Step, StructuredWorkout, Target
from app.tests.conftest import ctx_for


def _sw():
    return StructuredWorkout(
        name="Endurance 1h", ftp_watts=250.0,
        elements=[Step(intensity="active", duration_s=3600,
                       target=Target(type="power_pct_ftp", low=0.6, high=0.7))],
    )


@pytest.mark.asyncio
async def test_push_translates_and_sends(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    await GarminConnectionRepository(session, ctx).get_or_create()
    fc = FakeGarminClient()
    wid = await sync_push(session, ctx, fc, a.id, _sw(), date(2026, 7, 1))
    assert wid == "garmin-workout-1"
    sent_dict, sent_date = fc.pushed[0]
    assert sent_dict["workoutName"] == "Endurance 1h"
    assert sent_date == date(2026, 7, 1)


@pytest.mark.asyncio
async def test_unpush_calls_unschedule(session, two_athletes):
    a, _ = two_athletes
    ctx = ctx_for(a)
    await GarminConnectionRepository(session, ctx).get_or_create()
    fc = FakeGarminClient()
    await sync_unpush(session, ctx, fc, "garmin-workout-9")
    assert "garmin-workout-9" in fc.unscheduled
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_sync_push.py -v`
Expected: FAIL — `ImportError: cannot import name 'sync_push'`.

- [ ] **Step 3: Implement `sync_push` / `sync_unpush`**

Adicionar a `backend/app/services/garmin/sync_service.py` (imports no topo + funções no fim):
```python
from app.services.garmin.workout_translator import to_garmin_workout  # topo
from app.services.workout.model import StructuredWorkout  # topo


async def _resume_or_reauth(session, ctx, client, athlete_id):
    conn_repo = GarminConnectionRepository(session, ctx)
    conn = await conn_repo.get_or_create(athlete_id)
    try:
        token = token_store.decrypt(conn.encrypted_token) if conn.encrypted_token else {}
        client.resume(token)
    except GarminAuthError as exc:
        await _mark_reauth(conn_repo, conn, str(exc))
        raise
    return conn, conn_repo


async def sync_push(session, ctx, client, athlete_id, sw: StructuredWorkout,
                    schedule_date) -> str:
    conn, conn_repo = await _resume_or_reauth(session, ctx, client, athlete_id)
    payload = to_garmin_workout(sw)
    wid = client.push_workout(payload, schedule_date)
    new_token = client.current_token()
    if new_token and token_store.is_enabled():
        conn.encrypted_token = token_store.encrypt(new_token)
    await session.flush()
    return wid


async def sync_unpush(session, ctx, client, garmin_workout_id: str) -> None:
    client.unschedule_workout(garmin_workout_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_sync_push.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/garmin/sync_service.py backend/app/tests/test_garmin/test_sync_push.py
git commit -m "feat(garmin): sync_push/sync_unpush (translate, schedule, unschedule)"
```

---

### Task 9: Celery job + Beat diário

**Files:**
- Create: `backend/app/jobs/garmin_job.py`
- Modify: `backend/app/jobs/celery_app.py` (import do módulo + beat schedule)
- Test: `backend/app/tests/test_garmin/test_job.py`

**Interfaces:**
- Consumes: `sync_pull`, `RealGarminClient`, `GarminConnectionRepository`, `AsyncSessionLocal`, `run_async`.
- Produces:
  - `async _do_sync(athlete_id: str, tenant_id: str) -> dict` (testável diretamente, sem Celery).
  - `sync_athlete_garmin(athlete_id, tenant_id)` (task Celery, nome `"garmin_sync"`).
  - `async enqueue_all_connected() -> int` opcional para o beat (itera atletas `CONNECTED`).

- [ ] **Step 1: Write the failing test**

`backend/app/tests/test_garmin/test_job.py`:
```python
"""A função interna do job roda o pull com um client injetado."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.enums import GarminConnectionStatus
from app.repositories.garmin_repo import GarminConnectionRepository
from app.services.garmin.fake_client import FakeGarminClient
from app.services.garmin.sync_service import sync_pull
from app.tests.conftest import ctx_for

_CSV = (
    b"date,duration_s,distance_m,avg_power,external_id\n"
    b"2026-06-30T06:00:00,3600,30000,200,garmin-act-1\n"
)


@pytest.mark.asyncio
async def test_pull_via_injected_client_sets_connected(session, two_athletes):
    # O job real instancia RealGarminClient; aqui validamos o núcleo testável
    # (sync_pull) que o job chama, com o Fake. O wiring Celery é fino e coberto
    # pela verificação manual.
    a, _ = two_athletes
    ctx = ctx_for(a)
    await GarminConnectionRepository(session, ctx).get_or_create()
    fc = FakeGarminClient(
        activities=[("garmin-act-1", datetime(2026, 6, 30, 6, tzinfo=timezone.utc))],
        fit_bytes=_CSV,
    )
    res = await sync_pull(session, ctx, fc, a.id)
    conn = await GarminConnectionRepository(session, ctx).get_for_athlete()
    assert conn.status is GarminConnectionStatus.CONNECTED
    assert res.activities_imported == 1
```

- [ ] **Step 2: Run test to verify it fails (then passes — núcleo já existe)**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_job.py -v`
Expected: PASS desde já (valida o núcleo que o job usa). Este teste protege contra regressões no contrato `sync_pull` que o job depende.

- [ ] **Step 3: Implement `garmin_job.py`**

`backend/app/jobs/garmin_job.py`:
```python
"""Celery job: pull Garmin (activities + wellness) for one athlete."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.tenant import TenantContext
from app.jobs._run import run_async
from app.models.enums import GarminConnectionStatus, Role
from app.models.garmin import GarminConnection
from app.services.garmin.client import GarminAuthError, RealGarminClient
from app.services.garmin.sync_service import sync_pull
from app.services.metrics.recompute import recompute_load_metrics


async def _do_sync(athlete_id: str, tenant_id: str) -> dict:
    aid = uuid.UUID(athlete_id)
    ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)
    async with AsyncSessionLocal() as session:
        try:
            result = await sync_pull(session, ctx, RealGarminClient(), aid)
        except GarminAuthError:
            await session.commit()  # persist needs_reauth marking
            return {"status": "needs_reauth"}
        await recompute_load_metrics(session, ctx, aid)
        await session.commit()
        return {
            "status": "ok",
            "activities_imported": result.activities_imported,
            "duplicates": result.duplicates,
            "wellness_days": result.wellness_days,
        }


def sync_athlete_garmin(athlete_id: str, tenant_id: str) -> dict:
    return run_async(_do_sync(athlete_id, tenant_id))


async def _enqueue_all_connected() -> int:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(GarminConnection).where(
                GarminConnection.status == GarminConnectionStatus.CONNECTED,
                GarminConnection.deleted_at.is_(None),
            )
        )
        count = 0
        for conn in rows.scalars().all():
            sync_athlete_garmin.delay(str(conn.athlete_id), "")  # tenant resolved in job
            count += 1
        return count


def beat_sync_all() -> int:
    return run_async(_enqueue_all_connected())


try:
    from app.jobs.celery_app import celery

    sync_athlete_garmin = celery.task(name="garmin_sync")(sync_athlete_garmin)  # type: ignore[assignment]
    beat_sync_all = celery.task(name="garmin_beat_sync_all")(beat_sync_all)  # type: ignore[assignment]
except Exception:  # noqa: BLE001 — importable without a broker (tests)
    pass
```

> **NOTA:** o `tenant_id` precisa ser resolvido para o atleta no `_do_sync`. Como o beat não tem o tenant à mão, ajuste: ou (a) buscar o `Athlete.tenant_id` por `athlete_id` no início de `_do_sync`, ou (b) gravar `tenant_id` na `GarminConnection`. Implementar (a): no `_do_sync`, antes de montar o `ctx`, carregar `tenant_id = (await session.get(Athlete, aid)).tenant_id`. Atualizar a assinatura para aceitar `tenant_id: str | None` e resolver quando vazio.

- [ ] **Step 4: Apply the tenant-resolution fix in `_do_sync`**

Substituir o início de `_do_sync` por:
```python
async def _do_sync(athlete_id: str, tenant_id: str | None = None) -> dict:
    aid = uuid.UUID(athlete_id)
    async with AsyncSessionLocal() as session:
        from app.models.athlete import Athlete
        if not tenant_id:
            ath = await session.get(Athlete, aid)
            tenant_id = ath.tenant_id if ath else ""
        ctx = TenantContext(athlete_id=aid, tenant_id=tenant_id, role=Role.ATHLETE)
        ...  # restante igual
```

- [ ] **Step 5: Register the job + beat schedule in `celery_app.py`**

Em `backend/app/jobs/celery_app.py`, na linha de imports finais, adicionar `garmin_job`:
```python
from app.jobs import import_job, metrics_job, profile_job, garmin_job  # noqa: E402,F401
```
E adicionar o beat schedule após `celery.conf.update(...)`:
```python
celery.conf.beat_schedule = {
    "garmin-daily-sync": {
        "task": "garmin_beat_sync_all",
        "schedule": 24 * 60 * 60.0,  # daily
    },
}
```

- [ ] **Step 6: Run test + import check**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_job.py -v && python -c "import app.jobs.garmin_job"`
Expected: teste PASS; import sem erro.

- [ ] **Step 7: Commit**

```bash
git add backend/app/jobs/garmin_job.py backend/app/jobs/celery_app.py backend/app/tests/test_garmin/test_job.py
git commit -m "feat(garmin): Celery sync job + daily beat schedule"
```

---

### Task 10: Rotas da API + schemas + wiring (deps, router, feature flag)

**Files:**
- Create: `backend/app/schemas/garmin.py`
- Create: `backend/app/api/routes/garmin.py`
- Modify: `backend/app/main.py:70-72` (registrar o router)
- Modify: `backend/pyproject.toml` (deps)
- Test: `backend/app/tests/test_garmin/test_api.py`

**Interfaces:**
- Consumes: `get_tenant`, `get_db`, `GarminConnectionRepository`, `token_store`, `RealGarminClient` (injetável p/ teste), `sync_athlete_garmin`.
- Produces: rotas `POST /garmin/connect`, `POST /garmin/connect/mfa`, `POST /garmin/sync`, `GET /garmin/status`, `DELETE /garmin/disconnect`. Todas 503 se `token_store.is_enabled()` for False.

- [ ] **Step 1: Write the failing test**

`backend/app/tests/test_garmin/test_api.py`:
```python
"""Rotas Garmin: fluxo connect/mfa, status, isolamento por tenant, feature-flag."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_tenant
from app.core.database import get_db
from app.main import app
from app.services.garmin import token_store
from app.services.garmin.fake_client import FakeGarminClient
from app.api.routes import garmin as garmin_routes
from app.tests.conftest import ctx_for


@pytest.fixture
def client_factory(session, two_athletes, monkeypatch):
    a, _ = two_athletes
    monkeypatch.setattr(token_store.settings, "garmin_token_key",
                        __import__("cryptography.fernet", fromlist=["Fernet"])
                        .Fernet.generate_key().decode())
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_tenant] = lambda: ctx_for(a)

    def _make(fake: FakeGarminClient):
        monkeypatch.setattr(garmin_routes, "_new_client", lambda: fake)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
    yield _make
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_connect_needs_mfa_then_completes(client_factory):
    fake = FakeGarminClient(needs_mfa=True)
    async with client_factory(fake) as ac:
        r1 = await ac.post("/api/v1/garmin/connect",
                           json={"email": "e@x.com", "password": "pw"})
        assert r1.status_code == 200
        assert r1.json()["needs_mfa"] is True
        r2 = await ac.post("/api/v1/garmin/connect/mfa", json={"code": "123456"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "CONNECTED"


@pytest.mark.asyncio
async def test_status_reports_connection(client_factory):
    fake = FakeGarminClient(needs_mfa=False)
    async with client_factory(fake) as ac:
        await ac.post("/api/v1/garmin/connect",
                      json={"email": "e@x.com", "password": "pw"})
        r = await ac.get("/api/v1/garmin/status")
        assert r.json()["status"] == "CONNECTED"


@pytest.mark.asyncio
async def test_feature_disabled_returns_503(client_factory, monkeypatch):
    monkeypatch.setattr(token_store.settings, "garmin_token_key", "")
    fake = FakeGarminClient()
    async with client_factory(fake) as ac:
        r = await ac.get("/api/v1/garmin/status")
        assert r.status_code == 503
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest app/tests/test_garmin/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: app.api.routes.garmin`.

- [ ] **Step 3: Implement schemas**

`backend/app/schemas/garmin.py`:
```python
"""Request/response schemas for the Garmin sync endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GarminConnectRequest(BaseModel):
    email: str
    password: str


class GarminMfaRequest(BaseModel):
    code: str


class GarminConnectResponse(BaseModel):
    needs_mfa: bool
    status: str


class GarminStatusResponse(BaseModel):
    status: str
    last_sync_at: datetime | None = None
    needs_reauth: bool
    last_error: str | None = None


class GarminSyncResponse(BaseModel):
    task_id: str | None
```

- [ ] **Step 4: Implement the routes**

`backend/app/api/routes/garmin.py`:
```python
"""Garmin Connect sync endpoints. Disabled (503) when garmin_token_key is unset."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.tenant import TenantContext
from app.models.enums import GarminConnectionStatus
from app.repositories.garmin_repo import GarminConnectionRepository
from app.schemas.garmin import (
    GarminConnectRequest,
    GarminConnectResponse,
    GarminMfaRequest,
    GarminStatusResponse,
    GarminSyncResponse,
)
from app.services.garmin import token_store
from app.services.garmin.client import GarminAuthError, RealGarminClient
from app.services.garmin.types import Connected, NeedsMfa

router = APIRouter(prefix="/garmin", tags=["garmin"])
log = get_logger(__name__)

_MFA_TTL_MIN = 5


def _new_client():
    """Indirection so tests can inject a FakeGarminClient."""
    return RealGarminClient()


def _require_enabled() -> None:
    if not token_store.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Garmin sync is not configured",
        )


@router.post("/connect", response_model=GarminConnectResponse)
async def connect(
    body: GarminConnectRequest,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    repo = GarminConnectionRepository(db, ctx)
    conn = await repo.get_or_create()
    client = _new_client()
    try:
        result = client.login(body.email, body.password)
    except GarminAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    if isinstance(result, NeedsMfa):
        conn.mfa_state = token_store.encrypt(result.client_state)
        conn.mfa_expires_at = datetime.now(timezone.utc) + timedelta(minutes=_MFA_TTL_MIN)
        conn.status = GarminConnectionStatus.AWAITING_MFA
        await db.commit()
        return GarminConnectResponse(needs_mfa=True, status=conn.status.value)
    # Connected directly (no MFA)
    assert isinstance(result, Connected)
    conn.encrypted_token = token_store.encrypt(result.token)
    conn.status = GarminConnectionStatus.CONNECTED
    conn.connected_at = datetime.now(timezone.utc)
    conn.mfa_state = None
    await db.commit()
    return GarminConnectResponse(needs_mfa=False, status=conn.status.value)


@router.post("/connect/mfa", response_model=GarminConnectResponse)
async def connect_mfa(
    body: GarminMfaRequest,
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    repo = GarminConnectionRepository(db, ctx)
    conn = await repo.get_for_athlete()
    if conn is None or not conn.mfa_state:
        raise HTTPException(status_code=409, detail="no MFA in progress")
    if conn.mfa_expires_at and conn.mfa_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="MFA expired; restart connect")
    client = _new_client()
    client_state = token_store.decrypt(conn.mfa_state)
    try:
        token = client.resume_mfa(client_state, body.code)
    except GarminAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    conn.encrypted_token = token_store.encrypt(token)
    conn.status = GarminConnectionStatus.CONNECTED
    conn.connected_at = datetime.now(timezone.utc)
    conn.mfa_state = None
    conn.mfa_expires_at = None
    await db.commit()
    return GarminConnectResponse(needs_mfa=False, status=conn.status.value)


@router.get("/status", response_model=GarminStatusResponse)
async def get_status(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    conn = await GarminConnectionRepository(db, ctx).get_for_athlete()
    if conn is None:
        return GarminStatusResponse(
            status=GarminConnectionStatus.DISCONNECTED.value, needs_reauth=False
        )
    return GarminStatusResponse(
        status=conn.status.value,
        last_sync_at=conn.last_sync_at,
        needs_reauth=conn.status is GarminConnectionStatus.NEEDS_REAUTH,
        last_error=conn.last_error,
    )


@router.post("/sync", response_model=GarminSyncResponse)
async def trigger_sync(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    from app.jobs.garmin_job import sync_athlete_garmin

    task_id = None
    try:
        task = sync_athlete_garmin.delay(str(ctx.athlete_id), ctx.tenant_id)
        task_id = task.id
    except Exception:
        log.exception("garmin sync enqueue failed")
    return GarminSyncResponse(task_id=task_id)


@router.delete("/disconnect", status_code=204)
async def disconnect(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    repo = GarminConnectionRepository(db, ctx)
    conn = await repo.get_for_athlete()
    if conn is not None:
        conn.encrypted_token = None
        conn.mfa_state = None
        conn.status = GarminConnectionStatus.DISCONNECTED
        await db.commit()
```

- [ ] **Step 5: Register router + add deps**

Em `backend/app/main.py`, adicionar `garmin` ao import dos routers (linha que importa `auth, athletes, ...` de `app.api.routes`) e à tupla do loop (linha 70):
```python
for r in (auth, athletes, workouts, metrics, imports, races, plans,
          recommendations, feedback, admin, jobs, calendar, garmin):
```

Em `backend/pyproject.toml`, na lista `dependencies`, adicionar:
```toml
    "garminconnect>=0.3.6",
    "cryptography>=42",
```

- [ ] **Step 6: Install deps and run the API test**

Run: `cd backend && pip install -e . && python -m pytest app/tests/test_garmin/test_api.py -v`
Expected: PASS (3 passed). (Se o `httpx`/`ASGITransport` não estiver disponível, instalar `httpx` como dev dep; checar se outros `test_api` já o usam — se sim, já está disponível.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/garmin.py backend/app/api/routes/garmin.py backend/app/main.py backend/pyproject.toml backend/app/tests/test_garmin/test_api.py
git commit -m "feat(garmin): API routes (connect/mfa/sync/status/disconnect) + deps + wiring"
```

---

### Task 11: Suíte completa, lint e revisão final

**Files:** nenhum novo — verificação de integração.

- [ ] **Step 1: Run the full test suite**

Run: `cd backend && python -m pytest -q`
Expected: toda a suíte passa (incluindo `test_garmin/` e nenhuma regressão em `test_api`, `test_ingestion`, `test_jobs`).

- [ ] **Step 2: Lint/format conforme o projeto**

Run: `cd backend && ruff check app/ && ruff format --check app/`
Expected: sem erros. (Se o projeto usa outro linter, rodar o equivalente — checar `pyproject.toml`/`Makefile`.)

- [ ] **Step 3: Confirmar a migration de ponta a ponta (Postgres no ar)**

Run: `cd backend && alembic upgrade head`
Expected: revisão `0009` aplicada; `garmin_connections` existe.

- [ ] **Step 4: Self-review do plano vs spec**

Conferir que cada item do spec tem tarefa:
- import atividades → Task 7 ✓
- import wellness → Task 7 ✓
- export/agendar planejado → Task 6 + Task 8 ✓
- onboarding MFA 2 passos → Task 10 ✓
- token cifrado → Task 1 + Task 2 ✓
- detectar 401 → needs_reauth → Task 7 ✓
- Beat diário + sync on-demand → Task 9 + Task 10 ✓
- feature-flag (503) → Task 10 ✓
- isolamento por tenant → Task 3 + Task 10 ✓

- [ ] **Step 5: Commit final (se houver ajustes de lint)**

```bash
git add -A
git commit -m "chore(garmin): lint/format + suíte verde"
```

---

## Verificação manual (gate do piloto — fora do código, ver spec §7)

1. Gerar `garmin_token_key` e pôr no `.env`; subir API + worker + beat.
2. `POST /garmin/connect` com credenciais reais de 1 atleta → responder MFA em `/connect/mfa` → `status=CONNECTED`.
3. `POST /garmin/sync` → conferir atividade real + wellness do dia importados; rodar de novo não duplica.
4. Aceitar/gerar um treino → conferir que aparece **agendado** no calendário do Garmin do atleta.
5. Reverter o treino → some do calendário.
6. Forçar token inválido → `GET /status` mostra `needs_reauth: true`.
