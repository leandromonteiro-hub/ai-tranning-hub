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
