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
