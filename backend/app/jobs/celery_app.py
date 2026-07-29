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

from app.jobs import import_job, metrics_job, profile_job, garmin_job, health_job  # noqa: E402,F401

# Alerta imediato quando QUALQUER task estoura (ver app/jobs/health_job.py).
from celery.signals import task_failure  # noqa: E402

task_failure.connect(health_job.alert_task_failure, weak=False)

celery.conf.beat_schedule = {
    "garmin-daily-sync": {
        "task": "garmin_beat_sync_all",
        "schedule": 24 * 60 * 60.0,  # daily
    },
    "monitoring-heartbeat": {
        "task": "monitoring_heartbeat",
        "schedule": 900.0,  # 15 min — grace de 20 min no healthchecks.io
    },
}
