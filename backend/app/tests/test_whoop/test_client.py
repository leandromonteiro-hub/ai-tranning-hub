"""O client traduz a semântica da Whoop para a nossa, e nunca vaza exceção crua.

Três regras da API que, ignoradas, gravariam lixo como se fosse medição:
- recovery não tem data: ela aponta para o sono por sleep_id
- nap=true é cochilo, não a noite
- score_state != SCORED significa que o score não existe ou está incompleto
"""
from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.services.whoop import client as whoop_client
from app.services.whoop.types import WhoopAuthError, WhoopRateLimited

_TOKEN = {"access_token": "at", "refresh_token": "rt", "expires_at": 9_999_999_999}


def _sleep(sid, start, end, offset="-03:00", nap=False, state="SCORED", perf=88, stages=None):
    return {
        "id": sid, "start": start, "end": end, "timezone_offset": offset,
        "nap": nap, "score_state": state,
        "score": {
            "sleep_performance_percentage": perf,
            "stage_summary": stages or {
                "total_light_sleep_time_milli": 3 * 3_600_000,
                "total_slow_wave_sleep_time_milli": 2 * 3_600_000,
                "total_rem_sleep_time_milli": 1 * 3_600_000,
                "total_awake_time_milli": 30 * 60_000,
            },
        },
    }


def _recovery(sleep_id, hrv=61.5, rhr=48, score=72, state="SCORED"):
    return {
        "sleep_id": sleep_id, "cycle_id": 1, "score_state": state,
        "score": {"hrv_rmssd_milli": hrv, "resting_heart_rate": rhr, "recovery_score": score},
    }


def _transport(sleeps, recoveries):
    def handler(request: httpx.Request) -> httpx.Response:
        if "/activity/sleep" in request.url.path:
            return httpx.Response(200, json={"records": sleeps, "next_token": None})
        if "/recovery" in request.url.path:
            return httpx.Response(200, json={"records": recoveries, "next_token": None})
        raise AssertionError(f"URL inesperada: {request.url}")
    return httpx.MockTransport(handler)


def test_metric_date_is_the_local_wake_up_day():
    """Dormiu 23h de segunda, acordou 6h de terça => o dado é de TERÇA."""
    sleeps = [_sleep("s1", "2026-07-27T02:00:00Z", "2026-07-28T09:00:00Z")]
    # fim 09:00Z com offset -03:00 => 06:00 local do dia 28
    c = whoop_client.WhoopClient(_TOKEN, transport=_transport(sleeps, [_recovery("s1")]))

    days = c.fetch_days(date(2026, 7, 27), date(2026, 7, 28))

    assert [d.metric_date for d in days] == [date(2026, 7, 28)]


def test_offset_can_change_the_day():
    """Fim às 01:00Z com offset -03:00 é 22:00 do dia ANTERIOR no fuso do atleta."""
    sleeps = [_sleep("s1", "2026-07-27T14:00:00Z", "2026-07-28T01:00:00Z")]
    c = whoop_client.WhoopClient(_TOKEN, transport=_transport(sleeps, [_recovery("s1")]))

    assert c.fetch_days(date(2026, 7, 27), date(2026, 7, 28))[0].metric_date == date(2026, 7, 27)


def test_sleep_hours_sums_only_asleep_stages():
    """3h leve + 2h profundo + 1h REM = 6h. Acordado não é sono."""
    sleeps = [_sleep("s1", "2026-07-27T02:00:00Z", "2026-07-28T09:00:00Z")]
    c = whoop_client.WhoopClient(_TOKEN, transport=_transport(sleeps, [_recovery("s1")]))

    assert c.fetch_days(date(2026, 7, 27), date(2026, 7, 28))[0].snapshot.sleep_hours == 6.0


def test_naps_are_discarded():
    sleeps = [_sleep("s1", "2026-07-28T14:00:00Z", "2026-07-28T15:00:00Z", nap=True)]
    c = whoop_client.WhoopClient(_TOKEN, transport=_transport(sleeps, [_recovery("s1")]))

    assert c.fetch_days(date(2026, 7, 28), date(2026, 7, 28)) == []


def test_unscored_records_are_discarded():
    sleeps = [_sleep("s1", "2026-07-27T02:00:00Z", "2026-07-28T09:00:00Z", state="PENDING_SCORE")]
    c = whoop_client.WhoopClient(_TOKEN, transport=_transport(sleeps, [_recovery("s1")]))

    assert c.fetch_days(date(2026, 7, 27), date(2026, 7, 28)) == []


def test_recovery_without_matching_sleep_is_skipped():
    """Sem o sono correspondente não há data — gravar num dia chutado seria pior."""
    sleeps = [_sleep("s1", "2026-07-27T02:00:00Z", "2026-07-28T09:00:00Z")]
    c = whoop_client.WhoopClient(_TOKEN, transport=_transport(sleeps, [_recovery("SEM-PAR")]))

    day = c.fetch_days(date(2026, 7, 27), date(2026, 7, 28))[0]
    assert day.snapshot.sleep_hours == 6.0
    assert day.snapshot.hrv_ms is None  # sono entrou, recuperação não


def test_pagination_follows_next_token():
    page1 = [_sleep("s1", "2026-07-26T02:00:00Z", "2026-07-27T09:00:00Z")]
    page2 = [_sleep("s2", "2026-07-27T02:00:00Z", "2026-07-28T09:00:00Z")]
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "/recovery" in request.url.path:
            return httpx.Response(200, json={"records": [], "next_token": None})
        if "nextToken=tok2" in str(request.url):
            return httpx.Response(200, json={"records": page2, "next_token": None})
        return httpx.Response(200, json={"records": page1, "next_token": "tok2"})

    c = whoop_client.WhoopClient(_TOKEN, transport=httpx.MockTransport(handler))
    days = c.fetch_days(date(2026, 7, 26), date(2026, 7, 28))

    assert len(days) == 2
    assert any("nextToken=tok2" in u for u in calls)


def test_401_becomes_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_token"})

    c = whoop_client.WhoopClient(_TOKEN, transport=httpx.MockTransport(handler))
    with pytest.raises(WhoopAuthError):
        c.fetch_days(date(2026, 7, 28), date(2026, 7, 28))


def test_429_carries_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"X-RateLimit-Reset": "37"})

    c = whoop_client.WhoopClient(_TOKEN, transport=httpx.MockTransport(handler))
    with pytest.raises(WhoopRateLimited) as exc:
        c.fetch_days(date(2026, 7, 28), date(2026, 7, 28))
    assert exc.value.retry_after_s == 37


def test_authorize_url_carries_state_and_scopes(monkeypatch):
    monkeypatch.setattr(whoop_client.settings, "whoop_client_id", "cid")

    url = whoop_client.authorize_url("st8", "https://app.example/api/whoop/callback")

    assert url.startswith("https://api.prod.whoop.com/oauth/oauth2/auth?")
    assert "state=st8" in url
    assert "read%3Arecovery" in url and "read%3Asleep" in url and "offline" in url
