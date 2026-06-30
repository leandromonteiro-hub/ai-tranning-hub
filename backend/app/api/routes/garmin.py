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
    if not isinstance(result, Connected):
        raise HTTPException(status_code=500, detail="unexpected login result")
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
    if conn.mfa_expires_at:
        expires = conn.mfa_expires_at
        if expires.tzinfo is None:  # SQLite strips tzinfo; treat as UTC
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
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
    # Inline import to avoid circular import at module load time.
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
