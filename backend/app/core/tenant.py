"""Tenant isolation primitives.

Isolation is enforced at the *service/repository* layer, not just the route.
Every athlete-scoped query passes through a ``TenantContext`` whose ``athlete_id``
is derived from the authenticated principal. The repository base (see
``app.repositories.base``) requires this context and injects an
``athlete_id == ctx.athlete_id`` filter on every read and write, making it
impossible to address another tenant's rows without an explicit, audited
admin override.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models.enums import Role


class TenantViolationError(Exception):
    """Raised when an operation attempts to cross tenant boundaries."""


@dataclass(frozen=True)
class TenantContext:
    """Resolved identity + tenant for the current request."""

    athlete_id: uuid.UUID
    tenant_id: str
    role: Role

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    def assert_can_access(self, target_athlete_id: uuid.UUID) -> None:
        """Guard used by services before touching athlete-scoped data."""
        if self.is_admin:
            return
        if target_athlete_id != self.athlete_id:
            raise TenantViolationError(
                "Cross-tenant access denied: principal "
                f"{self.athlete_id} cannot access athlete {target_athlete_id}"
            )
