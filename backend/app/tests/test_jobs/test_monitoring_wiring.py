"""O alerta só existe se estiver ligado no beat e no sinal.

Sem a entrada no beat_schedule o heartbeat nunca roda; sem o connect() o
task_failure nunca alerta. Os dois são uma linha fácil de perder num rebase, e
a falha seria silenciosa — exatamente o modo de falha que este trabalho ataca.
"""
from __future__ import annotations

from celery.signals import task_failure

from app.jobs import health_job
from app.jobs.celery_app import celery


def test_heartbeat_is_scheduled_every_15_minutes():
    entry = celery.conf.beat_schedule["monitoring-heartbeat"]
    assert entry["task"] == "monitoring_heartbeat"
    assert entry["schedule"] == 900.0


def test_daily_garmin_sync_is_still_scheduled():
    """A entrada nova não pode substituir o beat_schedule existente."""
    assert celery.conf.beat_schedule["garmin-daily-sync"]["task"] == "garmin_beat_sync_all"


def test_task_failure_signal_reaches_the_alert(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        health_job, "ping_monitor", lambda url, *a, **kw: calls.append((url, kw))
    )
    monkeypatch.setattr(health_job.settings, "monitor_failure_url", "https://hc/fail-uuid")

    class _Sender:
        name = "garmin_sync"

    task_failure.send(sender=_Sender(), task_id="abc-123", exception=ValueError("boom"))

    assert len(calls) == 1
    assert calls[0][0] == "https://hc/fail-uuid"
    assert calls[0][1]["suffix"] == "/fail"
