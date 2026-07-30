"""Rotas da integração Whoop: autorizar, callback, status, sincronizar, desconectar.

Feature desligada (client_id/secret vazios) responde 503 em todas — o card do web
some e nada quebra. Mesmo padrão do Garmin e do login com Google.
"""
from __future__ import annotations

import uuid
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
    # site_address entra na checagem porque sem ele o redirect_uri sai como
    # "https:///api/whoop/callback" — a Whoop recusaria, e o erro apareceria só
    # no meio do fluxo do atleta em vez de aqui.
    if not (
        settings.whoop_client_id
        and settings.whoop_client_secret
        and settings.site_address
    ):
        raise HTTPException(status_code=503, detail="whoop_disabled")


def _redirect_uri() -> str:
    return f"https://{settings.site_address}/api/whoop/callback"


async def _connection(db: AsyncSession, athlete_id: uuid.UUID) -> WhoopConnection | None:
    return (await db.execute(
        select(WhoopConnection).where(
            WhoopConnection.athlete_id == athlete_id,
            WhoopConnection.deleted_at.is_(None),
        )
    )).scalar_one_or_none()


@router.get("/status", response_model=WhoopStatusRead)
async def status(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
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
        # o 11º atleta bate. Detalhe específico para não depurar isso às cegas.
        log.warning("whoop: troca de código falhou: %s", exc)
        raise HTTPException(status_code=403, detail="whoop_authorization_failed") from exc
    except WhoopSyncError as exc:
        raise HTTPException(status_code=502, detail="whoop_unavailable") from exc

    conn = await _connection(db, ctx.athlete_id)
    if conn is None:
        conn = WhoopConnection(athlete_id=ctx.athlete_id)
        db.add(conn)
    conn.encrypted_token = token_store.encrypt(token)
    conn.status = WhoopConnectionStatus.CONNECTED
    conn.connected_at = datetime.now(timezone.utc)
    conn.last_error = None
    needs_backfill = conn.backfilled_at is None
    await db.commit()

    if needs_backfill:
        try:
            from app.jobs.whoop_job import backfill_whoop

            backfill_whoop.delay(str(ctx.athlete_id), ctx.tenant_id)
        except Exception:  # noqa: BLE001 — broker fora nunca derruba a conexão
            log.exception("whoop: enfileirar backfill falhou; conexão mantida")

    return WhoopStatusRead(
        status=WhoopConnectionStatus.CONNECTED.value,
        connected_at=conn.connected_at,
    )


@router.post("/sync", status_code=202)
async def sync_now(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    conn = await _connection(db, ctx.athlete_id)
    if conn is None or conn.status is not WhoopConnectionStatus.CONNECTED:
        raise HTTPException(status_code=409, detail="not_connected")
    from app.jobs.whoop_job import sync_whoop

    task = sync_whoop.delay(str(ctx.athlete_id), ctx.tenant_id)
    return {"task_id": task.id}


@router.delete("/connection", status_code=204)
async def disconnect(
    ctx: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    conn = await _connection(db, ctx.athlete_id)
    if conn is not None:
        conn.status = WhoopConnectionStatus.DISCONNECTED
        conn.encrypted_token = None  # o token sai do banco na hora
        await db.commit()
