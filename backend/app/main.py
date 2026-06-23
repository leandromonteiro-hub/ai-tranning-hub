"""FastAPI application entrypoint for Athlete AI Training Hub."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import (
    admin,
    athletes,
    auth,
    feedback,
    imports,
    metrics,
    plans,
    races,
    recommendations,
    workouts,
)
from app.bootstrap import ensure_admin, ensure_pgvector, ensure_prompt_templates
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import AuditMiddleware, RateLimitMiddleware

configure_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", extra={"environment": settings.environment})
    await ensure_pgvector()
    await ensure_admin()
    await ensure_prompt_templates()
    yield
    log.info("shutdown")


app = FastAPI(
    title="Athlete AI Training Hub",
    version="0.1.0",
    description="AI-driven cycling/MTB endurance training management system",
    lifespan=lifespan,
)

# Order matters: rate limit first, then audit (audit records the final status).
app.add_middleware(AuditMiddleware)
app.add_middleware(RateLimitMiddleware)


@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "service": "athlete-ai-training-hub", "version": "0.1.0"}


@app.get("/", tags=["system"])
async def root() -> dict:
    return {"name": "Athlete AI Training Hub", "docs": "/docs"}


_p = settings.api_prefix
for r in (auth, athletes, workouts, metrics, imports, races, plans,
          recommendations, feedback, admin):
    app.include_router(r.router, prefix=_p)
