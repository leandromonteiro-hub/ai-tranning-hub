"""Audit logging and simple per-user rate limiting middleware."""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.security import safe_decode_token
from app.models.audit import AuditLog

log = get_logger(__name__)

# Endpoints that must never be rate-limited or noisily audited.
_SKIP_PATHS = {"/health", "/", "/docs", "/openapi.json", "/redoc"}

# Only mutating verbs are persisted to the audit log.
_AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window per-user (or per-IP) rate limiter. In-memory (single proc)."""

    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _key(self, request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            payload = safe_decode_token(auth[7:])
            if payload and payload.get("sub"):
                return f"user:{payload['sub']}"
        client = request.client.host if request.client else "unknown"
        return f"ip:{client}"

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        key = self._key(request)
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        window.append(now)
        return await call_next(request)


class AuditMiddleware(BaseHTTPMiddleware):
    """Persist an immutable audit record for every mutating request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if request.method not in _AUDIT_METHODS or request.url.path in _SKIP_PATHS:
            return response

        actor_id = None
        actor_role = None
        tenant_id = None
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            payload = safe_decode_token(auth[7:])
            if payload:
                try:
                    actor_id = uuid.UUID(payload["sub"])
                except (KeyError, ValueError):
                    actor_id = None
                actor_role = payload.get("role")
                tenant_id = payload.get("tenant_id")

        try:
            async with AsyncSessionLocal() as session:
                session.add(
                    AuditLog(
                        actor_athlete_id=actor_id,
                        actor_role=actor_role,
                        tenant_id=tenant_id,
                        method=request.method,
                        endpoint=request.url.path,
                        action=f"{request.method} {request.url.path}",
                        target_athlete_id=actor_id,
                        ip_address=request.client.host if request.client else None,
                        status_code=response.status_code,
                    )
                )
                await session.commit()
        except Exception:  # noqa: BLE001 — auditing must never break the request
            log.exception("audit_write_failed")
        return response
