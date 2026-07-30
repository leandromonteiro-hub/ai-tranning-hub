"""Sem a entrada no beat o sync nunca roda, e a falha é silenciosa.

O cron às 08:00 UTC (05:00 no Brasil) existe para o dado da noite estar pronto
antes de o atleta gerar o treino do dia. Uma janela em intervalo de 24h, como a
do garmin-daily-sync, não garante hora — por isso este é crontab.
"""
from __future__ import annotations

from celery.schedules import crontab

from app.jobs.celery_app import celery


def test_whoop_sync_is_scheduled_at_8_utc():
    entry = celery.conf.beat_schedule["whoop-daily-sync"]
    assert entry["task"] == "whoop_beat_sync_all"
    assert entry["schedule"] == crontab(hour=8, minute=0)


def test_existing_schedules_survive():
    """A entrada nova não pode substituir as que já existem."""
    keys = set(celery.conf.beat_schedule)
    assert {"garmin-daily-sync", "monitoring-heartbeat"} <= keys


def test_tasks_are_registered_with_the_expected_names():
    """As rotas e o beat referenciam a task pelo nome — errar aqui é falha silenciosa."""
    import app.jobs.whoop_job  # noqa: F401 — registra as tasks

    assert {"whoop_sync", "whoop_backfill", "whoop_beat_sync_all"} <= set(celery.tasks)
