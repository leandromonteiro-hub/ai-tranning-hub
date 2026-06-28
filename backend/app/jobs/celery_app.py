"""Celery application for async import / metrics / embedding jobs."""
from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery = Celery(
    "athlete_hub",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=900,
)

# Ensure task modules are imported so Celery registers them.
celery.autodiscover_tasks(["app.jobs"])

from app.jobs import import_job, metrics_job, profile_job  # noqa: E402,F401
