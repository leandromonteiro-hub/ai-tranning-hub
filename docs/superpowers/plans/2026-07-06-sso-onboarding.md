# SSO Google + Convites + Onboarding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-cadastro (Google SSO + email/senha) gated por código de convite, e wizard de onboarding `/bem-vindo` (anamnese obrigatória + Garmin opcional) para o piloto de 10 atletas.

**Architecture:** O botão oficial do Google (GIS) devolve um ID token no browser; um novo endpoint FastAPI verifica a assinatura (lib `google-auth`, verificador injetável via Protocol) e emite o JWT próprio do app — o cookie `aath_token` de hoje continua sendo a única sessão. Convites são tabela própria com consumo transacional. O gate de onboarding vive no layout servidor do grupo `(app)`, e o wizard num grupo de rota próprio.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic; `google-auth`; Next.js 15 App Router + SWR + vitest.

**Spec:** `docs/superpowers/specs/2026-07-06-sso-onboarding-design.md`

## Global Constraints

- UI inteira em **pt-BR**; reusar `Card`/`Button`/`Input`/`Badge` de `web/components/ui/`.
- Testes backend SÓ via Docker (não há Python no host):
  `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest <PATH> -q --no-header -p no:warnings"`
- Testes web no host: `cd web && npx vitest run <PATH>`.
- Branch: `feat/sso-onboarding` (já existe, spec commitada).
- Commits terminam com `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Códigos de convite: 8 chars do alfabeto `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (sem 0/O/1/I), armazenados/validados em MAIÚSCULO, uso único.
- Detalhes de erro do `/auth/google` para conta nova (verbatim, o web depende deles): `"invite_required"` e `"invite_invalid"`.
- Mensagem do login por senha em conta só-Google (verbatim): `"Esta conta usa Entrar com Google."`
- `google_client_id` vazio ⇒ `/auth/google` responde 503; `NEXT_PUBLIC_GOOGLE_CLIENT_ID` ausente ⇒ botão Google não renderiza.

---

### Task 1: Backend — migration 0010, modelos e serviço de convites

**Files:**
- Create: `backend/alembic/versions/0010_sso_invites.py`
- Create: `backend/app/services/auth/__init__.py` (vazio)
- Create: `backend/app/services/auth/invites.py`
- Modify: `backend/app/models/athlete.py` (Athlete: 3 campos)
- Create: `backend/app/models/invite.py`
- Modify: `backend/app/models/__init__.py` (registrar InviteCode)
- Test: `backend/app/tests/test_auth_sso/__init__.py` (vazio) e `backend/app/tests/test_auth_sso/test_invites.py`

**Interfaces:**
- Produces: `Athlete.google_sub: str | None`, `Athlete.hashed_password: str | None` (agora nullable), `Athlete.onboarding_completed_at: datetime | None`. `InviteCode` (Base): `code`, `used_by_athlete_id`, `used_at`, `expires_at`. Serviço `app.services.auth.invites`: `generate_code() -> str`, `async create_invites(session, created_by: uuid.UUID | None, count: int) -> list[InviteCode]`, `async find_valid(session, code: str) -> InviteCode | None`, `consume(invite: InviteCode, athlete_id: uuid.UUID) -> None`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/app/tests/test_auth_sso/__init__.py` vazio e `backend/app/tests/test_auth_sso/test_invites.py`:

```python
"""Convites de uso único: geração, validação case-insensitive, consumo, expiração."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services.auth import invites

_ALPHABET = set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")


def test_generate_code_format():
    for _ in range(50):
        code = invites.generate_code()
        assert len(code) == 8
        assert set(code) <= _ALPHABET  # sem 0/O/1/I


@pytest.mark.asyncio
async def test_create_and_find_valid_is_case_insensitive(session):
    created = await invites.create_invites(session, created_by=None, count=2)
    assert len(created) == 2
    found = await invites.find_valid(session, created[0].code.lower())
    assert found is not None and found.id == created[0].id


@pytest.mark.asyncio
async def test_consume_makes_code_invalid(session, two_athletes):
    a, _ = two_athletes
    (inv,) = await invites.create_invites(session, created_by=None, count=1)
    invites.consume(inv, a.id)
    await session.flush()
    assert await invites.find_valid(session, inv.code) is None
    assert inv.used_by_athlete_id == a.id and inv.used_at is not None


@pytest.mark.asyncio
async def test_expired_code_is_invalid(session):
    (inv,) = await invites.create_invites(session, created_by=None, count=1)
    inv.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await session.flush()
    assert await invites.find_valid(session, inv.code) is None


@pytest.mark.asyncio
async def test_unknown_code_is_invalid(session):
    assert await invites.find_valid(session, "NAOEXIST") is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_auth_sso -q --no-header -p no:warnings"`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.auth'`

- [ ] **Step 3: Implementar modelos, serviço e migration**

Em `backend/app/models/athlete.py`, na classe `Athlete`, trocar a linha do `hashed_password` e adicionar dois campos (depois de `is_active`):

```python
    # Nullable: contas criadas via Google SSO não têm senha.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

```python
    # Vínculo com a conta Google (sub do ID token). Nullable = sem SSO.
    google_sub: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    # Wizard /bem-vindo concluído. NULL = ainda no onboarding.
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

e ajustar imports do módulo: `from datetime import date, datetime` e `from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text`.

Criar `backend/app/models/invite.py`:

```python
"""Convite de uso único para auto-cadastro (piloto controlado)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class InviteCode(Base):
    __tablename__ = "invite_codes"

    code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    used_by_athlete_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("athletes.id"), nullable=True
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Em `backend/app/models/__init__.py`, adicionar após o import de athlete:

```python
from app.models.invite import InviteCode
```

Criar `backend/app/services/auth/__init__.py` vazio e `backend/app/services/auth/invites.py`:

```python
"""Geração/validação/consumo de códigos de convite (uso único)."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invite import InviteCode

# Sem 0/O/1/I — códigos digitáveis sem ambiguidade.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


async def create_invites(
    session: AsyncSession, created_by: uuid.UUID | None, count: int
) -> list[InviteCode]:
    out = [InviteCode(code=generate_code(), created_by=created_by) for _ in range(count)]
    session.add_all(out)
    await session.flush()
    return out


async def find_valid(session: AsyncSession, code: str) -> InviteCode | None:
    stmt = select(InviteCode).where(
        InviteCode.code == code.strip().upper(),
        InviteCode.used_at.is_(None),
        InviteCode.deleted_at.is_(None),
    )
    inv = (await session.execute(stmt)).scalar_one_or_none()
    if inv is None:
        return None
    if inv.expires_at is not None:
        expires = inv.expires_at
        if expires.tzinfo is None:  # SQLite strips tzinfo; treat as UTC
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            return None
    return inv


def consume(invite: InviteCode, athlete_id: uuid.UUID) -> None:
    invite.used_by_athlete_id = athlete_id
    invite.used_at = datetime.now(timezone.utc)
```

Criar `backend/alembic/versions/0010_sso_invites.py`:

```python
"""SSO Google + convites + onboarding state

Revision ID: 0010
Revises: 0009
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athletes", sa.Column("google_sub", sa.String(length=64), nullable=True))
    op.create_index("ix_athletes_google_sub", "athletes", ["google_sub"], unique=True)
    op.alter_column("athletes", "hashed_password", existing_type=sa.String(length=255), nullable=True)
    op.add_column(
        "athletes",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Atletas existentes não caem no wizard.
    op.execute("UPDATE athletes SET onboarding_completed_at = NOW()")

    op.create_table(
        "invite_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("used_by_athlete_id", UUID(as_uuid=True), sa.ForeignKey("athletes.id"), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_invite_codes_code", "invite_codes", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_invite_codes_code", table_name="invite_codes")
    op.drop_table("invite_codes")
    op.drop_column("athletes", "onboarding_completed_at")
    op.alter_column("athletes", "hashed_password", existing_type=sa.String(length=255), nullable=False)
    op.drop_index("ix_athletes_google_sub", table_name="athletes")
    op.drop_column("athletes", "google_sub")
```

- [ ] **Step 4: Rodar e ver passar (+ suíte de repositórios para regressão do modelo)**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_auth_sso app/tests/test_repositories app/tests/test_isolation -q --no-header -p no:warnings; ruff check app/models app/services/auth app/tests/test_auth_sso alembic/versions/0010_sso_invites.py"`
Expected: tudo verde + `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0010_sso_invites.py backend/app/models/athlete.py backend/app/models/invite.py backend/app/models/__init__.py backend/app/services/auth backend/app/tests/test_auth_sso
git commit -m "feat(auth): migration 0010 — google_sub, senha nullable, onboarding state e convites

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Backend — GoogleVerifier (Protocol + Real + Fake) e config

**Files:**
- Create: `backend/app/services/auth/google_verifier.py`
- Modify: `backend/app/core/config.py` (campo `google_client_id`)
- Modify: `backend/pyproject.toml` (dep `google-auth`)
- Modify: `.env.example` (GOOGLE_CLIENT_ID)
- Test: `backend/app/tests/test_auth_sso/test_google_verifier.py`

**Interfaces:**
- Produces: `GoogleIdentity` (dataclass: `sub: str, email: str, email_verified: bool, name: str`), `GoogleAuthError(RuntimeError)`, `GoogleVerifier` Protocol com `verify(credential: str) -> GoogleIdentity`, `RealGoogleVerifier`, `FakeGoogleVerifier(identity=None, error=False)`. `settings.google_client_id: str = ""`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/app/tests/test_auth_sso/test_google_verifier.py`:

```python
"""FakeGoogleVerifier: contrato do Protocol usado pelas rotas (Real é adapter de rede)."""
from __future__ import annotations

import pytest

from app.services.auth.google_verifier import (
    FakeGoogleVerifier,
    GoogleAuthError,
    GoogleIdentity,
)


def test_fake_returns_configured_identity():
    ident = GoogleIdentity(sub="g-123", email="x@gmail.com", email_verified=True, name="X")
    fake = FakeGoogleVerifier(identity=ident)
    assert fake.verify("any-credential") == ident


def test_fake_raises_when_configured_as_error():
    fake = FakeGoogleVerifier(error=True)
    with pytest.raises(GoogleAuthError):
        fake.verify("bad")


def test_settings_default_google_client_id_empty():
    from app.core.config import Settings
    assert Settings(_env_file=None).google_client_id == ""
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_auth_sso/test_google_verifier.py -q --no-header -p no:warnings"`
Expected: FAIL — `ModuleNotFoundError` (google_verifier não existe)

- [ ] **Step 3: Implementar**

Criar `backend/app/services/auth/google_verifier.py`:

```python
"""Verificação de ID token do Google. RealGoogleVerifier é o ÚNICO lugar que
importa google-auth; rotas dependem do Protocol e testam com o Fake."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


class GoogleAuthError(RuntimeError):
    """ID token inválido (assinatura/aud/iss/exp)."""


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str


class GoogleVerifier(Protocol):
    def verify(self, credential: str) -> GoogleIdentity: ...


class RealGoogleVerifier:
    def verify(self, credential: str) -> GoogleIdentity:
        from google.auth.transport import requests as google_requests  # lazy
        from google.oauth2 import id_token

        try:
            info = id_token.verify_oauth2_token(
                credential, google_requests.Request(), settings.google_client_id
            )
        except Exception as exc:  # noqa: BLE001 — qualquer falha => token inválido
            raise GoogleAuthError(f"invalid google credential: {exc}") from exc
        return GoogleIdentity(
            sub=str(info["sub"]),
            email=info.get("email", ""),
            email_verified=bool(info.get("email_verified")),
            name=info.get("name") or info.get("email", ""),
        )


class FakeGoogleVerifier:
    def __init__(self, identity: GoogleIdentity | None = None, error: bool = False):
        self._identity = identity
        self._error = error

    def verify(self, credential: str) -> GoogleIdentity:
        if self._error or self._identity is None:
            raise GoogleAuthError("fake: invalid credential")
        return self._identity
```

Em `backend/app/core/config.py`, adicionar depois do bloco do `garmin_token_key`:

```python
    # Google SSO. Vazio => login com Google desligado (rota /auth/google responde 503).
    google_client_id: str = ""
```

Em `backend/pyproject.toml`, adicionar à lista de dependencies (junto das outras):

```toml
    "google-auth>=2.28",
```

Em `.env.example`, adicionar após o bloco do Garmin:

```
# --- Google SSO ---
# OAuth Client ID (tipo Web) do Google Cloud Console. Vazio = SSO desligado.
# O MESMO valor vai no web como NEXT_PUBLIC_GOOGLE_CLIENT_ID (web/.env.local em dev).
GOOGLE_CLIENT_ID=
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_auth_sso -q --no-header -p no:warnings; ruff check app/services/auth app/core/config.py app/tests/test_auth_sso"`
Expected: verde + `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth/google_verifier.py backend/app/core/config.py backend/pyproject.toml .env.example backend/app/tests/test_auth_sso/test_google_verifier.py
git commit -m "feat(auth): GoogleVerifier injetável (Protocol/Real/Fake) + GOOGLE_CLIENT_ID

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Backend — /auth/signup, conta só-Google no login e claim email no JWT

**Files:**
- Modify: `backend/app/api/routes/auth.py`
- Modify: `backend/app/core/security.py` (`create_access_token` ganha `email`)
- Modify: `backend/app/schemas/auth.py` (`SignupRequest`)
- Test: `backend/app/tests/test_auth_sso/test_signup.py`

**Interfaces:**
- Consumes: `invites.find_valid/consume` (Task 1).
- Produces: `POST /auth/signup` `{full_name, email, password(min 8), invite_code}` → 201 `TokenResponse`; 409 email duplicado; 403 convite inválido. `POST /auth/login` em conta com `hashed_password IS NULL` → 400 `"Esta conta usa Entrar com Google."`. Access token passa a carregar claim `email`. `_tokens_for` inalterado na assinatura (usa `athlete.email` internamente).

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/app/tests/test_auth_sso/test_signup.py`:

```python
"""Auto-cadastro por senha gated por convite + login em conta só-Google + claim email."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import safe_decode_token
from app.main import app
from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role
from app.services.auth import invites


@pytest_asyncio.fixture
async def client_and_maker():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _override_get_db():
        async with maker() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, maker
    app.dependency_overrides.clear()
    await engine.dispose()


async def _make_invite(maker) -> str:
    async with maker() as s:
        (inv,) = await invites.create_invites(s, created_by=None, count=1)
        code = inv.code
        await s.commit()
    return code


@pytest.mark.asyncio
async def test_signup_with_valid_invite_creates_athlete(client_and_maker):
    client, maker = client_and_maker
    code = await _make_invite(maker)
    r = await client.post("/api/v1/auth/signup", json={
        "full_name": "Novo Atleta", "email": "novo@x.com",
        "password": "senha12345", "invite_code": code.lower(),
    })
    assert r.status_code == 201
    token = r.json()["access_token"]
    payload = safe_decode_token(token)
    assert payload["email"] == "novo@x.com"  # claim email agora presente
    # convite consumido: segundo uso falha
    r2 = await client.post("/api/v1/auth/signup", json={
        "full_name": "Outro", "email": "outro@x.com",
        "password": "senha12345", "invite_code": code,
    })
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_signup_invalid_invite_403(client_and_maker):
    client, _ = client_and_maker
    r = await client.post("/api/v1/auth/signup", json={
        "full_name": "X", "email": "x@x.com", "password": "senha12345",
        "invite_code": "NAOEXIST",
    })
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_signup_duplicate_email_409(client_and_maker):
    client, maker = client_and_maker
    code1 = await _make_invite(maker)
    code2 = await _make_invite(maker)
    body = {"full_name": "X", "email": "dup@x.com", "password": "senha12345"}
    assert (await client.post("/api/v1/auth/signup", json={**body, "invite_code": code1})).status_code == 201
    r = await client.post("/api/v1/auth/signup", json={**body, "invite_code": code2})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_password_login_on_google_only_account_400(client_and_maker):
    client, maker = client_and_maker
    async with maker() as s:
        s.add(Athlete(email="g@x.com", hashed_password=None, full_name="G",
                      role=Role.ATHLETE, tenant_id="tg", google_sub="g-1"))
        await s.commit()
    r = await client.post("/api/v1/auth/login",
                          data={"username": "g@x.com", "password": "qualquer"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Esta conta usa Entrar com Google."
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_auth_sso/test_signup.py -q --no-header -p no:warnings"`
Expected: FAIL — 404 no /auth/signup e asserts de claim/400

- [ ] **Step 3: Implementar**

Em `backend/app/core/security.py`, trocar `create_access_token` por (email com default para compat):

```python
def create_access_token(
    subject: str, role: str, tenant_id: str, athlete_id: str, email: str = ""
) -> str:
    return _create_token(
        subject,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        {"role": role, "tenant_id": tenant_id, "athlete_id": athlete_id, "email": email},
    )
```

Em `backend/app/schemas/auth.py`, adicionar:

```python
class SignupRequest(BaseModel):
    full_name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)
    invite_code: str = Field(min_length=1)
```

Em `backend/app/api/routes/auth.py`:

1. `_tokens_for`: adicionar `email=athlete.email,` na chamada de `create_access_token`.
2. No `login`, ANTES do check de credenciais, tratar conta só-Google:

```python
    repo = AthleteRepository(db)
    athlete = await repo.get_by_email(form.username)
    if athlete and athlete.hashed_password is None:
        raise HTTPException(status_code=400, detail="Esta conta usa Entrar com Google.")
    if not athlete or not verify_password(form.password, athlete.hashed_password):
        ...  # inalterado
```

3. Nova rota (após `register_athlete`), com imports de `invites` e `SignupRequest`:

```python
@router.post("/signup", response_model=TokenResponse, status_code=201)
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Auto-cadastro público, gated por código de convite de uso único."""
    invite = await invites.find_valid(db, req.invite_code)
    if invite is None:
        raise HTTPException(status_code=403, detail="invite_invalid")
    repo = AthleteRepository(db)
    if await repo.get_by_email(req.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    athlete = Athlete(
        email=req.email,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        role=Role.ATHLETE,
        tenant_id=f"tenant_{uuid.uuid4().hex[:12]}",
    )
    await repo.add(athlete)
    invites.consume(invite, athlete.id)
    return _tokens_for(athlete)
```

Imports novos em auth.py: `from app.models.enums import Role`, `from app.services.auth import invites`, e `SignupRequest` no bloco de schemas.

- [ ] **Step 4: Rodar e ver passar (+ regressão de auth existente)**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_auth_sso app/tests/test_api -q --no-header -p no:warnings; ruff check app/api/routes/auth.py app/core/security.py app/schemas/auth.py app/tests/test_auth_sso"`
Expected: verde + `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/auth.py backend/app/core/security.py backend/app/schemas/auth.py backend/app/tests/test_auth_sso/test_signup.py
git commit -m "feat(auth): POST /auth/signup com convite; 400 p/ conta só-Google; claim email no JWT

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Backend — POST /auth/google (login / linking / criação com convite)

**Files:**
- Modify: `backend/app/api/routes/auth.py`
- Modify: `backend/app/schemas/auth.py` (`GoogleLoginRequest`)
- Modify: `backend/app/repositories/athlete_repo.py` (`get_by_google_sub`)
- Test: `backend/app/tests/test_auth_sso/test_google_login.py`

**Interfaces:**
- Consumes: `GoogleVerifier`/`FakeGoogleVerifier`/`GoogleIdentity`/`GoogleAuthError` (Task 2); `invites` (Task 1).
- Produces: `POST /auth/google` `{credential, invite_code?}` → `TokenResponse`. Indireção `_new_verifier()` em auth.py (monkeypatchável). `AthleteRepository.get_by_google_sub(sub: str) -> Athlete | None`. Erros: 503 feature off; 401 token inválido; 403 `detail="invite_required"` (conta nova sem código) / `"invite_invalid"` (código ruim) / `"Email do Google não verificado."` (linking bloqueado); 403 conta inativa.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/app/tests/test_auth_sso/test_google_login.py`:

```python
"""POST /auth/google: login por sub, linking por email verificado, criação com convite."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.routes import auth as auth_routes
from app.core.database import get_db
from app.main import app
from app.models import Base
from app.models.athlete import Athlete
from app.models.enums import Role
from app.services.auth import invites
from app.services.auth.google_verifier import FakeGoogleVerifier, GoogleIdentity

IDENT = GoogleIdentity(sub="g-42", email="ciclista@gmail.com", email_verified=True, name="Ciclista")


@pytest_asyncio.fixture
async def client_and_maker(monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings.google_client_id", "test-client-id"
    )
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _override_get_db():
        async with maker() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, maker
    app.dependency_overrides.clear()
    await engine.dispose()


def _use_verifier(monkeypatch, verifier):
    monkeypatch.setattr(auth_routes, "_new_verifier", lambda: verifier)


@pytest.mark.asyncio
async def test_new_account_without_invite_403_invite_required(client_and_maker, monkeypatch):
    client, _ = client_and_maker
    _use_verifier(monkeypatch, FakeGoogleVerifier(identity=IDENT))
    r = await client.post("/api/v1/auth/google", json={"credential": "tok"})
    assert r.status_code == 403
    assert r.json()["detail"] == "invite_required"


@pytest.mark.asyncio
async def test_new_account_with_invite_creates_and_logs_in(client_and_maker, monkeypatch):
    client, maker = client_and_maker
    _use_verifier(monkeypatch, FakeGoogleVerifier(identity=IDENT))
    async with maker() as s:
        (inv,) = await invites.create_invites(s, created_by=None, count=1)
        code = inv.code
        await s.commit()
    r = await client.post("/api/v1/auth/google",
                          json={"credential": "tok", "invite_code": code})
    assert r.status_code == 200
    assert "access_token" in r.json()
    # segundo login pelo mesmo sub: sem convite, direto
    r2 = await client.post("/api/v1/auth/google", json={"credential": "tok"})
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_bad_invite_403_invite_invalid(client_and_maker, monkeypatch):
    client, _ = client_and_maker
    _use_verifier(monkeypatch, FakeGoogleVerifier(identity=IDENT))
    r = await client.post("/api/v1/auth/google",
                          json={"credential": "tok", "invite_code": "NAOEXIST"})
    assert r.status_code == 403
    assert r.json()["detail"] == "invite_invalid"


@pytest.mark.asyncio
async def test_links_google_to_existing_password_account(client_and_maker, monkeypatch):
    client, maker = client_and_maker
    _use_verifier(monkeypatch, FakeGoogleVerifier(identity=IDENT))
    async with maker() as s:
        s.add(Athlete(email=IDENT.email, hashed_password="x", full_name="Ja Existia",
                      role=Role.ATHLETE, tenant_id="t-old"))
        await s.commit()
    r = await client.post("/api/v1/auth/google", json={"credential": "tok"})
    assert r.status_code == 200
    async with maker() as s:
        from sqlalchemy import select
        ath = (await s.execute(select(Athlete).where(Athlete.email == IDENT.email))).scalar_one()
        assert ath.google_sub == IDENT.sub


@pytest.mark.asyncio
async def test_unverified_email_does_not_link(client_and_maker, monkeypatch):
    client, maker = client_and_maker
    unverified = GoogleIdentity(sub="g-9", email="x@gmail.com", email_verified=False, name="X")
    _use_verifier(monkeypatch, FakeGoogleVerifier(identity=unverified))
    async with maker() as s:
        s.add(Athlete(email="x@gmail.com", hashed_password="x", full_name="X",
                      role=Role.ATHLETE, tenant_id="t-x"))
        await s.commit()
    r = await client.post("/api/v1/auth/google", json={"credential": "tok"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_invalid_credential_401(client_and_maker, monkeypatch):
    client, _ = client_and_maker
    _use_verifier(monkeypatch, FakeGoogleVerifier(error=True))
    r = await client.post("/api/v1/auth/google", json={"credential": "bad"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_feature_off_503(client_and_maker, monkeypatch):
    client, _ = client_and_maker
    monkeypatch.setattr("app.core.config.settings.google_client_id", "")
    r = await client.post("/api/v1/auth/google", json={"credential": "tok"})
    assert r.status_code == 503
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_auth_sso/test_google_login.py -q --no-header -p no:warnings"`
Expected: FAIL — 404 na rota / AttributeError `_new_verifier`

- [ ] **Step 3: Implementar**

Em `backend/app/schemas/auth.py`:

```python
class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1)
    invite_code: str | None = None
```

Em `backend/app/repositories/athlete_repo.py`, adicionar método:

```python
    async def get_by_google_sub(self, google_sub: str) -> Athlete | None:
        stmt = select(Athlete).where(
            Athlete.google_sub == google_sub, Athlete.deleted_at.is_(None)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()
```

Em `backend/app/api/routes/auth.py`, adicionar imports (`from app.core.config import settings`, `GoogleLoginRequest` no bloco de schemas, e):

```python
from app.services.auth.google_verifier import GoogleAuthError, RealGoogleVerifier
```

e a rota + indireção:

```python
def _new_verifier():
    """Indireção para os testes injetarem FakeGoogleVerifier."""
    return RealGoogleVerifier()


@router.post("/google", response_model=TokenResponse)
async def google_login(
    req: GoogleLoginRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Login/cadastro com Google: verifica o ID token no servidor e emite o JWT do app."""
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google SSO is not configured")
    try:
        ident = _new_verifier().verify(req.credential)
    except GoogleAuthError:
        raise HTTPException(status_code=401, detail="Invalid Google credential")

    repo = AthleteRepository(db)
    athlete = await repo.get_by_google_sub(ident.sub)
    if athlete is None:
        existing = await repo.get_by_email(ident.email)
        if existing is not None:
            # Linking: só com email verificado pelo Google.
            if not ident.email_verified:
                raise HTTPException(status_code=403, detail="Email do Google não verificado.")
            existing.google_sub = ident.sub
            athlete = existing
        else:
            if not req.invite_code:
                raise HTTPException(status_code=403, detail="invite_required")
            invite = await invites.find_valid(db, req.invite_code)
            if invite is None:
                raise HTTPException(status_code=403, detail="invite_invalid")
            athlete = Athlete(
                email=ident.email,
                hashed_password=None,
                full_name=ident.name,
                role=Role.ATHLETE,
                tenant_id=f"tenant_{uuid.uuid4().hex[:12]}",
                google_sub=ident.sub,
            )
            await repo.add(athlete)
            invites.consume(invite, athlete.id)
    if not athlete.is_active:
        raise HTTPException(status_code=403, detail="Inactive account")
    return _tokens_for(athlete)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_auth_sso -q --no-header -p no:warnings; ruff check app/api/routes/auth.py app/schemas/auth.py app/repositories/athlete_repo.py app/tests/test_auth_sso"`
Expected: verde + `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/auth.py backend/app/schemas/auth.py backend/app/repositories/athlete_repo.py backend/app/tests/test_auth_sso/test_google_login.py
git commit -m "feat(auth): POST /auth/google — login por sub, linking por email verificado, criação com convite

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Backend — onboarding state em /auth/me + complete-onboarding + rotas admin de convites

**Files:**
- Modify: `backend/app/api/routes/auth.py` (`/me` e `/me/complete-onboarding`)
- Modify: `backend/app/api/routes/admin.py` (invites)
- Modify: `backend/app/schemas/auth.py` (`MeResponse`, `InviteRead`, `InviteCreateRequest`)
- Test: `backend/app/tests/test_auth_sso/test_onboarding_and_invites_admin.py`

**Interfaces:**
- Consumes: `invites.create_invites` (Task 1); fixture pattern das Tasks 3-4.
- Produces: `GET /auth/me` → `MeResponse` (CurrentUser + `onboarding_completed: bool`). `POST /auth/me/complete-onboarding` → 204, idempotente. `POST /admin/invites` body `{count: int = 1}` (1..50) → 201 `list[InviteRead]`; `GET /admin/invites` → `list[InviteRead]` com `code, used_by_email: str | None, used_at, created_at`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/app/tests/test_auth_sso/test_onboarding_and_invites_admin.py`:

```python
"""Onboarding state via /auth/me + complete-onboarding; CRUD admin de convites."""
from __future__ import annotations

from datetime import datetime, timezone

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


@pytest_asyncio.fixture
async def client_and_maker():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        s.add_all([
            Athlete(email="novo@x.com", hashed_password=hash_password("pw12345678"),
                    full_name="Novo", role=Role.ATHLETE, tenant_id="tn"),
            Athlete(email="antigo@x.com", hashed_password=hash_password("pw12345678"),
                    full_name="Antigo", role=Role.ATHLETE, tenant_id="tv",
                    onboarding_completed_at=datetime.now(timezone.utc)),
            Athlete(email="admin@x.com", hashed_password=hash_password("pw12345678"),
                    full_name="Admin", role=Role.ADMIN, tenant_id="tadm",
                    onboarding_completed_at=datetime.now(timezone.utc)),
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, maker
    app.dependency_overrides.clear()
    await engine.dispose()


async def _login(client, email: str) -> dict:
    r = await client.post("/api/v1/auth/login",
                          data={"username": email, "password": "pw12345678"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_me_reports_onboarding_state_and_complete_is_idempotent(client_and_maker):
    client, _ = client_and_maker
    h = await _login(client, "novo@x.com")
    assert (await client.get("/api/v1/auth/me", headers=h)).json()["onboarding_completed"] is False
    assert (await client.post("/api/v1/auth/me/complete-onboarding", headers=h)).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=h)).json()["onboarding_completed"] is True
    # idempotente
    assert (await client.post("/api/v1/auth/me/complete-onboarding", headers=h)).status_code == 204

    h2 = await _login(client, "antigo@x.com")
    assert (await client.get("/api/v1/auth/me", headers=h2)).json()["onboarding_completed"] is True


@pytest.mark.asyncio
async def test_admin_creates_and_lists_invites(client_and_maker):
    client, _ = client_and_maker
    h = await _login(client, "admin@x.com")
    r = await client.post("/api/v1/admin/invites", json={"count": 3}, headers=h)
    assert r.status_code == 201
    codes = [i["code"] for i in r.json()]
    assert len(codes) == 3 and all(len(c) == 8 for c in codes)
    listed = (await client.get("/api/v1/admin/invites", headers=h)).json()
    assert {i["code"] for i in listed} >= set(codes)
    assert all(i["used_by_email"] is None for i in listed if i["code"] in codes)


@pytest.mark.asyncio
async def test_invites_routes_are_admin_gated_and_count_capped(client_and_maker):
    client, _ = client_and_maker
    h = await _login(client, "novo@x.com")
    assert (await client.post("/api/v1/admin/invites", json={"count": 1}, headers=h)).status_code == 403
    hadm = await _login(client, "admin@x.com")
    assert (await client.post("/api/v1/admin/invites", json={"count": 51}, headers=hadm)).status_code == 422
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_auth_sso/test_onboarding_and_invites_admin.py -q --no-header -p no:warnings"`
Expected: FAIL — `onboarding_completed` ausente / 404 nas rotas novas

- [ ] **Step 3: Implementar**

Em `backend/app/schemas/auth.py`:

```python
class MeResponse(CurrentUser):
    onboarding_completed: bool


class InviteCreateRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=50)


class InviteRead(BaseModel):
    code: str
    used_by_email: str | None = None
    used_at: datetime | None = None
    created_at: datetime
```

(adicionar `from datetime import datetime` no topo do schemas/auth.py).

Em `backend/app/api/routes/auth.py`, substituir a rota `/me` e adicionar a nova (imports: `MeResponse` no bloco de schemas; `from datetime import datetime, timezone`):

```python
@router.get("/me", response_model=MeResponse)
async def me(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    athlete = await AthleteRepository(db).get(user.athlete_id)
    return MeResponse(
        **user.model_dump(),
        onboarding_completed=bool(athlete and athlete.onboarding_completed_at),
    )


@router.post("/me/complete-onboarding", status_code=204)
async def complete_onboarding(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    athlete = await AthleteRepository(db).get(user.athlete_id)
    if athlete is not None and athlete.onboarding_completed_at is None:
        athlete.onboarding_completed_at = datetime.now(timezone.utc)
        await db.commit()
```

Em `backend/app/api/routes/admin.py`, adicionar imports (`from app.models.invite import InviteCode`, `from app.schemas.auth import InviteCreateRequest, InviteRead`, `from app.services.auth import invites`, `from app.api.deps import require_admin` já existe) e rotas ao final:

```python
@router.post("/invites", response_model=list[InviteRead], status_code=201)
async def create_invites(
    req: InviteCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    created = await invites.create_invites(db, created_by=admin.athlete_id, count=req.count)
    await db.commit()
    return [InviteRead(code=i.code, created_at=i.created_at) for i in created]


@router.get("/invites", response_model=list[InviteRead])
async def list_invites(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(InviteCode, Athlete.email)
        .outerjoin(Athlete, InviteCode.used_by_athlete_id == Athlete.id)
        .where(InviteCode.deleted_at.is_(None))
        .order_by(InviteCode.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        InviteRead(code=i.code, used_by_email=email, used_at=i.used_at, created_at=i.created_at)
        for i, email in rows
    ]
```

Nota: `require_admin` já é dependência do router inteiro (`dependencies=[Depends(require_admin)]`); no `create_invites` ele entra de novo como parâmetro só para obter `admin.athlete_id`.

- [ ] **Step 4: Rodar e ver passar (suíte backend completa — é a última task de backend)**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests -q --no-header -p no:warnings 2>&1 | tail -2; ruff check app/"`
Expected: suíte inteira verde + `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/auth.py backend/app/api/routes/admin.py backend/app/schemas/auth.py backend/app/tests/test_auth_sso/test_onboarding_and_invites_admin.py
git commit -m "feat(auth): onboarding state no /auth/me + complete-onboarding + convites no admin

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Web — BFF routes (google/signup) + página /cadastro

**Files:**
- Create: `web/app/api/auth/google/route.ts`
- Create: `web/app/api/auth/signup/route.ts`
- Create: `web/components/auth/GoogleSignInButton.tsx`
- Create: `web/app/(auth)/cadastro/page.tsx`
- Create: `web/components/auth/CadastroForm.tsx`
- Modify: `web/middleware.ts` (tornar `/cadastro` público)
- Test: `web/components/auth/__tests__/CadastroForm.test.tsx` e `web/components/auth/__tests__/GoogleSignInButton.test.tsx`

**Interfaces:**
- Consumes: backend `POST auth/google` / `auth/signup` (Tasks 3-4); `resolveApiUrl`, `TOKEN_COOKIE`, `decodeJwtRole` de `@/lib/{config,session}`.
- Produces: `GoogleSignInButton({ onCredential: (credential: string) => void })` — renderiza `null` sem `NEXT_PUBLIC_GOOGLE_CLIENT_ID`. `CadastroForm()` client component. BFF `POST /api/auth/google` `{credential, invite_code?}` e `POST /api/auth/signup` `{full_name, email, password, invite_code}` — ambos setam o cookie e devolvem `{ok, role}`; erro devolve `{error: <detail do backend>}` com o mesmo status.

- [ ] **Step 1: Escrever os testes que falham**

Criar `web/components/auth/__tests__/GoogleSignInButton.test.tsx`:

```tsx
import { render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { GoogleSignInButton } from '@/components/auth/GoogleSignInButton'

afterEach(() => vi.unstubAllEnvs())

describe('GoogleSignInButton', () => {
  it('não renderiza nada sem NEXT_PUBLIC_GOOGLE_CLIENT_ID', () => {
    vi.stubEnv('NEXT_PUBLIC_GOOGLE_CLIENT_ID', '')
    const { container } = render(<GoogleSignInButton onCredential={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renderiza o container do botão quando o client id existe', () => {
    vi.stubEnv('NEXT_PUBLIC_GOOGLE_CLIENT_ID', 'cid-test')
    const { getByTestId } = render(<GoogleSignInButton onCredential={() => {}} />)
    expect(getByTestId('google-signin')).toBeInTheDocument()
  })
})
```

Criar `web/components/auth/__tests__/CadastroForm.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CadastroForm } from '@/components/auth/CadastroForm'

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }))
vi.mock('@/components/auth/GoogleSignInButton', () => ({
  GoogleSignInButton: () => <div data-testid="google-signin" />,
}))

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

beforeEach(() => {
  vi.restoreAllMocks()
})

function fill() {
  fireEvent.change(screen.getByLabelText('Nome completo'), { target: { value: 'Ana' } })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'ana@x.com' } })
  fireEvent.change(screen.getByLabelText('Senha (mínimo 8 caracteres)'), { target: { value: 'senha12345' } })
  fireEvent.change(screen.getByLabelText('Código de convite'), { target: { value: 'ABCD2345' } })
}

describe('CadastroForm', () => {
  it('botão desabilitado até preencher tudo', () => {
    render(<CadastroForm />)
    expect(screen.getByRole('button', { name: /Criar conta/ })).toBeDisabled()
    fill()
    expect(screen.getByRole('button', { name: /Criar conta/ })).toBeEnabled()
  })

  it('409 mostra mensagem de email já usado', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonRes({ error: 'dup' }, 409)))
    render(<CadastroForm />)
    fill()
    fireEvent.click(screen.getByRole('button', { name: /Criar conta/ }))
    expect(await screen.findByText('Este email já tem conta — use a página de login.')).toBeInTheDocument()
  })

  it('403 mostra mensagem de convite inválido', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonRes({ error: 'invite_invalid' }, 403)))
    render(<CadastroForm />)
    fill()
    fireEvent.click(screen.getByRole('button', { name: /Criar conta/ }))
    expect(await screen.findByText('Código de convite inválido ou já usado.')).toBeInTheDocument()
  })

  it('renderiza o botão Google', () => {
    render(<CadastroForm />)
    expect(screen.getByTestId('google-signin')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/auth`
Expected: FAIL — módulos inexistentes

- [ ] **Step 3: Implementar**

Criar `web/components/auth/GoogleSignInButton.tsx`:

```tsx
"use client";
import { useEffect, useRef } from 'react'

type GsiCredentialResponse = { credential: string }
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (cfg: { client_id: string; callback: (r: GsiCredentialResponse) => void }) => void
          renderButton: (el: HTMLElement, opts: Record<string, unknown>) => void
        }
      }
    }
  }
}

/** Botão oficial do Google (GIS). Sem NEXT_PUBLIC_GOOGLE_CLIENT_ID, não renderiza. */
export function GoogleSignInButton({ onCredential }: { onCredential: (credential: string) => void }) {
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID
  const host = useRef<HTMLDivElement>(null)
  const cb = useRef(onCredential)
  cb.current = onCredential

  useEffect(() => {
    if (!clientId) return
    const init = () => {
      if (!window.google || !host.current) return
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (r) => cb.current(r.credential),
      })
      window.google.accounts.id.renderButton(host.current, {
        theme: 'outline', size: 'large', width: 320, text: 'continue_with', locale: 'pt-BR',
      })
    }
    if (window.google?.accounts?.id) { init(); return }
    const s = document.createElement('script')
    s.src = 'https://accounts.google.com/gsi/client'
    s.async = true
    s.onload = init
    document.head.appendChild(s)
  }, [clientId])

  if (!clientId) return null
  return <div ref={host} data-testid="google-signin" className="flex justify-center" />
}
```

Criar `web/app/api/auth/google/route.ts`:

```ts
import { NextResponse } from "next/server";
import { resolveApiUrl } from "@/lib/config";
import { decodeJwtRole, TOKEN_COOKIE } from "@/lib/session";

export async function POST(request: Request) {
  let credential: string | undefined;
  let invite_code: string | undefined;
  try {
    ({ credential, invite_code } = await request.json());
  } catch {
    return NextResponse.json({ error: "Corpo inválido" }, { status: 400 });
  }
  const res = await fetch(resolveApiUrl("auth/google"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential, invite_code: invite_code ?? null }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return NextResponse.json({ error: body.detail ?? "Falha no login" }, { status: res.status });
  }
  const { access_token } = await res.json();
  const response = NextResponse.json({ ok: true, role: decodeJwtRole(access_token) ?? null });
  response.cookies.set(TOKEN_COOKIE, access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 30,
  });
  return response;
}
```

Criar `web/app/api/auth/signup/route.ts`:

```ts
import { NextResponse } from "next/server";
import { resolveApiUrl } from "@/lib/config";
import { decodeJwtRole, TOKEN_COOKIE } from "@/lib/session";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Corpo inválido" }, { status: 400 });
  }
  const res = await fetch(resolveApiUrl("auth/signup"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    return NextResponse.json({ error: err.detail ?? "Falha no cadastro" }, { status: res.status });
  }
  const { access_token } = await res.json();
  const response = NextResponse.json({ ok: true, role: decodeJwtRole(access_token) ?? null });
  response.cookies.set(TOKEN_COOKIE, access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 30,
  });
  return response;
}
```

Criar `web/components/auth/CadastroForm.tsx`:

```tsx
"use client";
import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { UserPlus } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { GoogleSignInButton } from '@/components/auth/GoogleSignInButton'

function signupError(status: number): string {
  if (status === 409) return 'Este email já tem conta — use a página de login.'
  if (status === 403) return 'Código de convite inválido ou já usado.'
  return 'Falha no cadastro. Tente novamente.'
}

export function CadastroForm() {
  const router = useRouter()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [invite, setInvite] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const canSubmit =
    fullName.trim() !== '' && email.trim() !== '' && password.length >= 8 &&
    invite.trim() !== '' && !loading

  async function finish(res: Response) {
    setLoading(false)
    if (res.ok) {
      router.push('/')
      router.refresh()
      return
    }
    setError(signupError(res.status))
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setLoading(true); setError('')
    const res = await fetch('/api/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        full_name: fullName, email, password, invite_code: invite.trim().toUpperCase(),
      }),
    })
    await finish(res)
  }

  async function onGoogle(credential: string) {
    if (invite.trim() === '') {
      setError('Preencha o código de convite antes de continuar com o Google.')
      return
    }
    setLoading(true); setError('')
    const res = await fetch('/api/auth/google', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential, invite_code: invite.trim().toUpperCase() }),
    })
    await finish(res)
  }

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      <Input label="Nome completo" value={fullName} onChange={(e) => setFullName(e.target.value)} />
      <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <Input
        label="Senha (mínimo 8 caracteres)"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="new-password"
      />
      <Input
        label="Código de convite"
        value={invite}
        onChange={(e) => setInvite(e.target.value)}
        placeholder="ex.: ABCD2345"
      />
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      <Button type="submit" className="w-full" disabled={!canSubmit}>
        <UserPlus className="h-4 w-4" />
        {loading ? 'Criando…' : 'Criar conta'}
      </Button>
      <div className="flex items-center gap-3 text-xs text-slate-400">
        <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" /> ou
        <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
      </div>
      <GoogleSignInButton onCredential={onGoogle} />
      <p className="text-center text-sm text-slate-500">
        Já tem conta? <a href="/login" className="underline">Entrar</a>
      </p>
    </form>
  )
}
```

Criar `web/app/(auth)/cadastro/page.tsx`:

```tsx
import { CadastroForm } from "@/components/auth/CadastroForm";

export default function CadastroPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 p-4">
      <div className="w-full max-w-md animate-fade-in">
        <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden">
          <div className="h-1.5" style={{ background: "var(--gradient-bar)" }} />
          <div className="p-8">
            <div className="flex flex-col items-center text-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo.svg" alt="" className="h-12 w-12" />
              <h1 className="mt-4 text-2xl font-bold text-slate-800 dark:text-slate-100">Criar conta</h1>
              <p className="mt-1 text-sm text-slate-500">
                O piloto é por convite — você recebeu um código do treinador.
              </p>
            </div>
            <div className="mt-8">
              <CadastroForm />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

Em `web/middleware.ts`, no bloco `isPublic`, adicionar as linhas do cadastro:

```ts
    pathname === "/cadastro" ||
    pathname.startsWith("/cadastro/") ||
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run components/auth`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add web/app/api/auth/google web/app/api/auth/signup web/components/auth web/app/\(auth\)/cadastro web/middleware.ts
git commit -m "feat(web): página /cadastro com convite + BFF google/signup + botão GIS

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Web — login com Google + link "Criar conta"

**Files:**
- Modify: `web/app/(auth)/login/page.tsx`
- Test: `web/app/(auth)/login/__tests__/LoginPage.test.tsx`

**Interfaces:**
- Consumes: `GoogleSignInButton` (Task 6); BFF `POST /api/auth/google` (Task 6).
- Produces: página de login com botão Google. Fluxo: `onCredential` → POST `{credential}` (sem convite); 403 com `error === "invite_required"` → `router.push('/cadastro?google=1')`. Email não vem mais pré-preenchido.

- [ ] **Step 1: Escrever os testes que falham**

Criar `web/app/(auth)/login/__tests__/LoginPage.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LoginPage from '@/app/(auth)/login/page'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }))

let capturedOnCredential: ((c: string) => void) | null = null
vi.mock('@/components/auth/GoogleSignInButton', () => ({
  GoogleSignInButton: ({ onCredential }: { onCredential: (c: string) => void }) => {
    capturedOnCredential = onCredential
    return <div data-testid="google-signin" />
  },
}))

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

beforeEach(() => {
  push.mockClear()
  capturedOnCredential = null
})

describe('LoginPage', () => {
  it('email não vem pré-preenchido e há link Criar conta + botão Google', () => {
    render(<LoginPage />)
    expect((screen.getByLabelText('Email') as HTMLInputElement).value).toBe('')
    expect(screen.getByRole('link', { name: /Criar conta/ })).toHaveAttribute('href', '/cadastro')
    expect(screen.getByTestId('google-signin')).toBeInTheDocument()
  })

  it('google com conta nova (invite_required) redireciona para /cadastro?google=1', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonRes({ error: 'invite_required' }, 403)))
    render(<LoginPage />)
    capturedOnCredential!('tok-google')
    await waitFor(() => expect(push).toHaveBeenCalledWith('/cadastro?google=1'))
  })

  it('google com conta existente entra e navega para /', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonRes({ ok: true, role: 'ATHLETE' })))
    render(<LoginPage />)
    capturedOnCredential!('tok-google')
    await waitFor(() => expect(push).toHaveBeenCalledWith('/'))
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run "app/(auth)/login"`
Expected: FAIL — email pré-preenchido / sem link / sem botão

- [ ] **Step 3: Implementar**

Em `web/app/(auth)/login/page.tsx`:

1. `useState("athlete1@athletehub.example.com")` → `useState("")`.
2. Import: `import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";`
3. Adicionar handler dentro do componente:

```tsx
  async function onGoogle(credential: string) {
    setLoading(true);
    setError("");
    const res = await fetch("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential }),
    });
    setLoading(false);
    if (res.ok) {
      const { role } = await res.json();
      router.push(role === "ADMIN" ? "/admin" : "/");
      router.refresh();
      return;
    }
    const body = await res.json().catch(() => ({ error: "" }));
    if (res.status === 403 && body.error === "invite_required") {
      router.push("/cadastro?google=1");
      return;
    }
    setError("Falha no login com Google. Tente novamente.");
  }
```

4. Após o `</form>`, adicionar:

```tsx
            <div className="mt-6 space-y-4">
              <div className="flex items-center gap-3 text-xs text-slate-400">
                <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" /> ou
                <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
              </div>
              <GoogleSignInButton onCredential={onGoogle} />
              <p className="text-center text-sm text-slate-500">
                Novo por aqui? <a href="/cadastro" className="underline">Criar conta</a>
              </p>
            </div>
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run "app/(auth)/login" components/auth`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add web/app/\(auth\)/login
git commit -m "feat(web): login com Google + link criar conta; remove email de dev pré-preenchido

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Web — wizard /bem-vindo + gate de onboarding no layout

**Files:**
- Create: `web/app/(onboarding)/bem-vindo/page.tsx`
- Create: `web/components/onboarding/OnboardingWizard.tsx`
- Modify: `web/app/(app)/layout.tsx` (gate)
- Test: `web/components/onboarding/__tests__/OnboardingWizard.test.tsx`

**Interfaces:**
- Consumes: `AnamneseView` de `@/components/anamnese/AnamneseView`; `GarminCard` de `@/components/importar/GarminCard`; `apiFetch` de `@/lib/api`; backend `GET auth/me` (`onboarding_completed`), `GET athletes/me/profile`, `POST auth/me/complete-onboarding` (Task 5).
- Produces: rota `/bem-vindo` (grupo próprio `(onboarding)`, sem sidebar; o middleware já exige cookie). Gate: `(app)/layout.tsx` consulta `auth/me` e faz `redirect("/bem-vindo")` quando `onboarding_completed === false`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `web/components/onboarding/__tests__/OnboardingWizard.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { OnboardingWizard } from '@/components/onboarding/OnboardingWizard'
import { apiFetch } from '@/lib/api'

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))
vi.mock('@/components/anamnese/AnamneseView', () => ({
  AnamneseView: () => <div data-testid="anamnese" />,
}))
vi.mock('@/components/importar/GarminCard', () => ({
  GarminCard: () => <div data-testid="garmin-card" />,
}))

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

beforeEach(() => vi.clearAllMocks())

describe('OnboardingWizard', () => {
  it('passo 1 não avança sem perfil salvo', async () => {
    ;(apiFetch as Mock).mockResolvedValue(jsonRes(null, 200))
    render(<OnboardingWizard />)
    expect(screen.getByTestId('anamnese')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Continuar/ }))
    expect(await screen.findByText('Salve sua anamnese antes de continuar.')).toBeInTheDocument()
    expect(screen.queryByTestId('garmin-card')).not.toBeInTheDocument()
  })

  it('passo 1 avança quando o perfil existe; passo 2 é pulável; concluir chama o endpoint', async () => {
    ;(apiFetch as Mock).mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === 'athletes/me/profile') return jsonRes({ weekly_hours: 8 })
      if (path === 'auth/me/complete-onboarding' && init?.method === 'POST') return jsonRes(null, 204)
      throw new Error(`unexpected ${path}`)
    })
    const origLocation = window.location
    Object.defineProperty(window, 'location', {
      value: { ...origLocation, href: '' }, writable: true,
    })
    render(<OnboardingWizard />)
    fireEvent.click(screen.getByRole('button', { name: /Continuar/ }))
    expect(await screen.findByTestId('garmin-card')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Pular por enquanto/ }))
    expect(screen.getByText(/Tudo pronto/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Começar a treinar/ }))
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('auth/me/complete-onboarding', expect.objectContaining({ method: 'POST' })))
    Object.defineProperty(window, 'location', { value: origLocation, writable: true })
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/onboarding`
Expected: FAIL — módulo inexistente

- [ ] **Step 3: Implementar**

Criar `web/components/onboarding/OnboardingWizard.tsx`:

```tsx
"use client";
import { useState } from 'react'
import { apiFetch } from '@/lib/api'
import { AnamneseView } from '@/components/anamnese/AnamneseView'
import { GarminCard } from '@/components/importar/GarminCard'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

const STEPS = ['Anamnese', 'Garmin', 'Concluir'] as const

export function OnboardingWizard() {
  const [step, setStep] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function advanceFromAnamnese() {
    setBusy(true); setError('')
    try {
      const res = await apiFetch('athletes/me/profile')
      const profile = res.ok ? await res.json() : null
      if (!profile) {
        setError('Salve sua anamnese antes de continuar.')
        return
      }
      setStep(1)
    } catch {
      setError('Não foi possível verificar seu perfil. Tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  async function complete() {
    setBusy(true); setError('')
    try {
      const res = await apiFetch('auth/me/complete-onboarding', { method: 'POST' })
      if (!res.ok) { setError('Não foi possível concluir. Tente novamente.'); return }
      // Reload completo: o gate do layout (server) precisa reavaliar o estado.
      window.location.href = '/'
    } catch {
      setError('Não foi possível concluir. Tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5 p-4 sm:p-8">
      <div className="flex items-center gap-2">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <span
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                i <= step ? 'bg-blue-600 text-white' : 'bg-slate-200 text-slate-500 dark:bg-slate-700'
              }`}
            >
              {i + 1}
            </span>
            <span className="text-sm text-slate-600 dark:text-slate-300">{label}</span>
            {i < STEPS.length - 1 && <span className="w-6 h-px bg-slate-300 dark:bg-slate-600" />}
          </div>
        ))}
      </div>

      {step === 0 && (
        <div className="space-y-4">
          <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">
            Bem-vindo! Primeiro, sua anamnese
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Sem ela o treinador IA não gera recomendações personalizadas.
          </p>
          <AnamneseView />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="button" onClick={advanceFromAnamnese} disabled={busy}>
            {busy ? 'Verificando…' : 'Continuar'}
          </Button>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-4">
          <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">
            Conecte seu Garmin (opcional)
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Importa seus treinos e recuperação automaticamente. Dá para fazer depois na página Importar.
          </p>
          <GarminCard />
          <div className="flex gap-2">
            <Button type="button" onClick={() => setStep(2)}>Continuar</Button>
            <Button type="button" variant="secondary" onClick={() => setStep(2)}>
              Pular por enquanto
            </Button>
          </div>
        </div>
      )}

      {step === 2 && (
        <Card title="Tudo pronto 🎉">
          <div className="space-y-4">
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Seu perfil está criado. Importe seus treinos históricos na página Importar
              para o treinador IA conhecer você mais rápido.
            </p>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button type="button" onClick={complete} disabled={busy}>
              {busy ? 'Concluindo…' : 'Começar a treinar'}
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}
```

Criar `web/app/(onboarding)/bem-vindo/page.tsx`:

```tsx
import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";

export default async function BemVindoPage() {
  const session = await getSession();
  if (!session) redirect("/login");
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <OnboardingWizard />
    </div>
  );
}
```

Em `web/app/(app)/layout.tsx`, adicionar o gate depois do fetch do nome (mesmo `try` novo, separado):

```tsx
  // Gate de onboarding: atleta sem wizard concluído vai para /bem-vindo.
  try {
    const meRes = await fetch(resolveApiUrl("auth/me"), {
      headers: { Authorization: `Bearer ${session.token}` },
      cache: "no-store",
    });
    if (meRes.ok && (await meRes.json()).onboarding_completed === false) {
      redirect("/bem-vindo");
    }
  } catch {
    // backend indisponível — não bloqueia; o gate reavalia na próxima navegação
  }
```

**ATENÇÃO (Next.js):** `redirect()` lança uma exceção interna (`NEXT_REDIRECT`) — dentro de `try/catch` ela seria engolida. Implementar com a decisão FORA do try:

```tsx
  let needsOnboarding = false;
  try {
    const meRes = await fetch(resolveApiUrl("auth/me"), {
      headers: { Authorization: `Bearer ${session.token}` },
      cache: "no-store",
    });
    if (meRes.ok) needsOnboarding = (await meRes.json()).onboarding_completed === false;
  } catch {
    // backend indisponível — não bloqueia
  }
  if (needsOnboarding) redirect("/bem-vindo");
```

(usar esta segunda forma; a primeira está aqui só para explicar o porquê).

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run components/onboarding`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add web/app/\(onboarding\) web/components/onboarding web/app/\(app\)/layout.tsx
git commit -m "feat(web): wizard /bem-vindo (anamnese obrigatória + Garmin opcional) + gate no layout

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Web — seção Convites no admin + suítes completas

**Files:**
- Create: `web/components/admin/InvitesSection.tsx`
- Modify: `web/components/admin/AdminView.tsx` (renderizar a seção)
- Modify: `web/lib/types.ts` (`Invite`)
- Modify: `web/lib/hooks.ts` (`useInvites`)
- Test: `web/components/admin/__tests__/InvitesSection.test.tsx`

**Interfaces:**
- Consumes: backend `GET/POST admin/invites` (Task 5); `jsonFetcher`/`apiFetch`.
- Produces: `Invite = { code: string; used_by_email: string | null; used_at: string | null; created_at: string }`; `useInvites()` (SWR em `admin/invites`); `<InvitesSection />` renderizada no AdminView.

- [ ] **Step 1: Escrever os testes que falham**

Criar `web/components/admin/__tests__/InvitesSection.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { InvitesSection } from '@/components/admin/InvitesSection'
import { useInvites } from '@/lib/hooks'
import { apiFetch } from '@/lib/api'

vi.mock('@/lib/hooks', () => ({ useInvites: vi.fn() }))
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

beforeEach(() => vi.clearAllMocks())

describe('InvitesSection', () => {
  it('lista códigos com status livre/usado', () => {
    ;(useInvites as Mock).mockReturnValue({
      data: [
        { code: 'ABCD2345', used_by_email: null, used_at: null, created_at: '2026-07-06T10:00:00Z' },
        { code: 'WXYZ7890', used_by_email: 'ana@x.com', used_at: '2026-07-06T11:00:00Z', created_at: '2026-07-06T09:00:00Z' },
      ],
      isLoading: false, mutate: vi.fn(),
    })
    render(<InvitesSection />)
    expect(screen.getByText('ABCD2345')).toBeInTheDocument()
    expect(screen.getByText('Livre')).toBeInTheDocument()
    expect(screen.getByText('ana@x.com')).toBeInTheDocument()
  })

  it('gerar convites chama o POST e revalida', async () => {
    const mutate = vi.fn()
    ;(useInvites as Mock).mockReturnValue({ data: [], isLoading: false, mutate })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes([{ code: 'NEW12345' }], 201))
    render(<InvitesSection />)
    fireEvent.click(screen.getByRole('button', { name: /Gerar 5 convites/ }))
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('admin/invites', expect.objectContaining({ method: 'POST' })))
    expect(mutate).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/admin/__tests__/InvitesSection.test.tsx`
Expected: FAIL — módulo inexistente

- [ ] **Step 3: Implementar**

Em `web/lib/types.ts`, adicionar ao final:

```ts
// --- Convites (admin) ---
export type Invite = {
  code: string
  used_by_email: string | null
  used_at: string | null
  created_at: string
}
```

Em `web/lib/hooks.ts`, adicionar `Invite` ao import de tipos e ao final:

```ts
export function useInvites() {
  return useSWR<Invite[]>('admin/invites', jsonFetcher as (p: string) => Promise<Invite[]>)
}
```

Criar `web/components/admin/InvitesSection.tsx`:

```tsx
"use client";
import { useState } from 'react'
import { Ticket } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { useInvites } from '@/lib/hooks'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

export function InvitesSection() {
  const { data, isLoading, mutate } = useInvites()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState<string | null>(null)

  async function generate() {
    setBusy(true); setError('')
    try {
      const res = await apiFetch('admin/invites', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: 5 }),
      })
      if (!res.ok) { setError('Falha ao gerar convites.'); return }
      await mutate()
    } catch {
      setError('Falha ao gerar convites.')
    } finally {
      setBusy(false)
    }
  }

  async function copy(code: string) {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(code)
      setTimeout(() => setCopied(null), 1500)
    } catch { /* clipboard indisponível — sem feedback */ }
  }

  return (
    <Card
      title={
        <span className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100">
          <Ticket className="h-4 w-4" /> Convites do piloto
        </span>
      }
      action={
        <Button type="button" onClick={generate} disabled={busy}>
          {busy ? 'Gerando…' : 'Gerar 5 convites'}
        </Button>
      }
    >
      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
      {isLoading ? (
        <p className="text-sm text-slate-500">Carregando…</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-400">
                <th className="font-normal">Código</th>
                <th className="font-normal">Status</th>
                <th className="font-normal">Usado por</th>
                <th className="font-normal" />
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((i) => (
                <tr key={i.code} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1.5 font-mono text-slate-700 dark:text-slate-200">{i.code}</td>
                  <td className="py-1.5">
                    {i.used_at ? <Badge variant="info">Usado</Badge> : <Badge variant="success">Livre</Badge>}
                  </td>
                  <td className="py-1.5 text-slate-500">{i.used_by_email ?? '—'}</td>
                  <td className="py-1.5 text-right">
                    {!i.used_at && (
                      <button
                        type="button"
                        onClick={() => copy(i.code)}
                        className="text-xs text-slate-500 underline hover:text-slate-700 dark:hover:text-slate-300"
                      >
                        {copied === i.code ? 'Copiado ✓' : 'Copiar'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(data ?? []).length === 0 && (
            <p className="py-2 text-sm text-slate-500">Nenhum convite ainda — gere os primeiros.</p>
          )}
        </div>
      )}
    </Card>
  )
}
```

Em `web/components/admin/AdminView.tsx`: adicionar `import { InvitesSection } from '@/components/admin/InvitesSection'` e renderizar `<InvitesSection />` como PRIMEIRO filho do container raiz da view (antes das seções existentes).

- [ ] **Step 4: Rodar as suítes completas (web + backend)**

Run: `cd web && npx vitest run 2>&1 | tail -3 && npm run lint --if-present`
Expected: suíte web inteira verde

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests -q --no-header -p no:warnings 2>&1 | tail -2"`
Expected: suíte backend inteira verde

- [ ] **Step 5: Commit**

```bash
git add web/components/admin web/lib/types.ts web/lib/hooks.ts
git commit -m "feat(web): seção de convites no painel admin

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
