"""Shared FastAPI dependencies: DB session, current user, tenant context, roles."""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import safe_decode_token
from app.core.tenant import TenantContext
from app.models.enums import Role
from app.schemas.auth import CurrentUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    payload = safe_decode_token(token)
    if not payload or payload.get("type") != "access":
        raise _CREDENTIALS_EXC
    try:
        return CurrentUser(
            athlete_id=uuid.UUID(payload["sub"]),
            email=payload.get("email", ""),
            role=Role(payload["role"]),
            tenant_id=payload["tenant_id"],
        )
    except (KeyError, ValueError):
        raise _CREDENTIALS_EXC


def get_tenant(user: CurrentUser = Depends(get_current_user)) -> TenantContext:
    """The tenant context that every athlete-scoped service call must carry."""
    return TenantContext(
        athlete_id=user.athlete_id, tenant_id=user.tenant_id, role=user.role
    )


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required"
        )
    return user


DbDep = Depends(get_db)
