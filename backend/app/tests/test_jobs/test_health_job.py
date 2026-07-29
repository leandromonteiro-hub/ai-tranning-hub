"""O heartbeat só pode pingar se o worker realmente conseguiu executar a task.

Regressão de 2026-07-28: o worker respondia `celery inspect ping` (o broker
estava OK) mas não conseguia executar NENHUMA task — `RuntimeError: can't start
new thread`. Um monitor que pingasse de fora teria ficado VERDE o incidente
inteiro. Por isso o ping vive dentro da task e só acontece DEPOIS de o caminho
real (run_async -> asyncio.run -> thread -> DB) ter dado certo.
"""
from __future__ import annotations

from app.core import database
from app.jobs import health_job


class _StubEngine:
    """run_async dispõe o engine global no fim; substituímos por um stub."""

    async def dispose(self) -> None:
        return None


def test_heartbeat_pings_when_the_db_answers(monkeypatch):
    monkeypatch.setattr(database, "engine", _StubEngine())

    async def fake_check_db():
        return None

    calls: list[tuple] = []
    monkeypatch.setattr(health_job, "_check_db", fake_check_db)
    monkeypatch.setattr(
        health_job,
        "ping_monitor",
        lambda url, *a, **kw: calls.append((url, a, kw)) or True,
    )
    monkeypatch.setattr(health_job.settings, "monitor_heartbeat_url", "https://hc/uuid")

    assert health_job.monitoring_heartbeat() == {"pinged": True}
    assert calls == [("https://hc/uuid", (), {})]


def test_heartbeat_does_not_ping_when_the_db_fails(monkeypatch):
    """DB fora => nenhum ping e a exceção SOBE (para o task_failure agir)."""
    monkeypatch.setattr(database, "engine", _StubEngine())

    async def fake_check_db():
        raise RuntimeError("can't start new thread")

    calls: list[str] = []
    monkeypatch.setattr(health_job, "_check_db", fake_check_db)
    monkeypatch.setattr(health_job, "ping_monitor", lambda url, *a, **kw: calls.append(url))
    monkeypatch.setattr(health_job.settings, "monitor_heartbeat_url", "https://hc/uuid")

    try:
        health_job.monitoring_heartbeat()
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("a exceção precisa subir para o task_failure disparar")
    assert calls == []


def test_alert_task_failure_pings_fail_with_task_name_and_exception(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        health_job, "ping_monitor", lambda url, *a, **kw: calls.append((url, a, kw))
    )
    monkeypatch.setattr(health_job.settings, "monitor_failure_url", "https://hc/fail-uuid")

    class _Sender:
        name = "garmin_sync"

    health_job.alert_task_failure(
        sender=_Sender(), task_id="abc-123", exception=ValueError("boom")
    )

    assert len(calls) == 1
    url, args, kwargs = calls[0]
    assert url == "https://hc/fail-uuid"
    assert kwargs["suffix"] == "/fail"
    assert "garmin_sync" in kwargs["body"]
    assert "abc-123" in kwargs["body"]
    assert "boom" in kwargs["body"]


def test_alert_task_failure_never_raises(monkeypatch):
    """Exceção dentro do handler mascararia o erro original da task."""

    def exploding_ping(*a, **kw):
        raise RuntimeError("monitor exploded")

    monkeypatch.setattr(health_job, "ping_monitor", exploding_ping)
    monkeypatch.setattr(health_job.settings, "monitor_failure_url", "https://hc/fail-uuid")

    try:
        health_job.alert_task_failure(
            sender=None, task_id=None, exception=ValueError("boom")
        )
    except Exception as exc:  # pragma: no cover
        raise AssertionError(f"o handler deixou vazar {exc!r}") from exc
