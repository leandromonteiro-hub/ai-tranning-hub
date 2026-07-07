"""Authentication routes: login, refresh, register (admin-gated for athletes)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    safe_decode_token,
    verify_password,
)
from app.models.athlete import Athlete
from app.models.enums import Role
from app.repositories.athlete_repo import AthleteRepository
from app.schemas.auth import (
    CurrentUser,
    GoogleLoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterAthleteRequest,
    SignupRequest,
    TokenResponse,
)
from app.services.auth import invites
from app.services.auth.google_verifier import GoogleAuthError, RealGoogleVerifier

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens_for(athlete: Athlete) -> TokenResponse:
    access = create_access_token(
        subject=str(athlete.id),
        role=athlete.role.value if hasattr(athlete.role, "value") else str(athlete.role),
        tenant_id=athlete.tenant_id,
        athlete_id=str(athlete.id),
        email=athlete.email,
    )
    refresh = create_refresh_token(subject=str(athlete.id))
    return TokenResponse(access_token=access, refresh_token=refresh)


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
            if not await invites.consume(db, invite.id, athlete.id):
                raise HTTPException(status_code=403, detail="invite_invalid")
    if not athlete.is_active:
        raise HTTPException(status_code=403, detail="Inactive account")
    return _tokens_for(athlete)


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    repo = AthleteRepository(db)
    athlete = await repo.get_by_email(form.username)
    if athlete and athlete.hashed_password is None:
        raise HTTPException(status_code=400, detail="Esta conta usa Entrar com Google.")
    if not athlete or not verify_password(form.password, athlete.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    if not athlete.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive account")
    return _tokens_for(athlete)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    payload = safe_decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    repo = AthleteRepository(db)
    athlete = await repo.get(uuid.UUID(payload["sub"]))
    if not athlete:
        raise HTTPException(status_code=401, detail="Unknown subject")
    return _tokens_for(athlete)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register_athlete(
    req: RegisterAthleteRequest,
    db: AsyncSession = Depends(get_db),
    _admin: CurrentUser = Depends(require_admin),
) -> TokenResponse:
    """Only an ADMIN may onboard a new athlete (controlled validation cohort)."""
    repo = AthleteRepository(db)
    if await repo.get_by_email(req.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    athlete = Athlete(
        email=req.email,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        role=req.role,
        tenant_id=f"tenant_{uuid.uuid4().hex[:12]}",
    )
    await repo.add(athlete)
    return _tokens_for(athlete)


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
    if not await invites.consume(db, invite.id, athlete.id):
        # corrida: outra transação usou o código entre find_valid e aqui
        raise HTTPException(status_code=403, detail="invite_invalid")
    return _tokens_for(athlete)


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
