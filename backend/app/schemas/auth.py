"""Auth-related Pydantic schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterAthleteRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: Role = Role.ATHLETE


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)
    invite_code: str = Field(min_length=1)


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1)
    invite_code: str | None = None


class CurrentUser(BaseModel):
    athlete_id: uuid.UUID
    email: str
    role: Role
    tenant_id: str


class MeResponse(CurrentUser):
    onboarding_completed: bool


class InviteCreateRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=50)


class InviteRead(BaseModel):
    code: str
    used_by_email: str | None = None
    used_at: datetime | None = None
    created_at: datetime
