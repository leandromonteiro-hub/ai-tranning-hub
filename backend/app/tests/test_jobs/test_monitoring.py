"""ping_monitor nunca pode derrubar o job que ele monitora.

Regressão que este módulo previne: em 2026-07-28 o worker ficou ~7 dias sem
executar nenhuma task e ninguém percebeu (PR #17). O ping é o sinal de vida —
mas um monitor que levanta exceção, ou que segura o worker esperando um
serviço externo, seria pior do que não ter monitor nenhum.
"""
from __future__ import annotations

import httpx

from app.core.monitoring import ping_monitor


def test_no_request_when_url_is_not_configured():
    """URL vazia => no-op silencioso. Dev, CI e prod-antes-da-conta não tocam a rede."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)

    assert ping_monitor(None, transport=transport) is False
    assert ping_monitor("", transport=transport) is False
    assert calls == []


def test_posts_to_the_configured_url():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    ok = ping_monitor(
        "https://hc-ping.example/uuid", transport=httpx.MockTransport(handler)
    )

    assert ok is True
    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert str(calls[0].url) == "https://hc-ping.example/uuid"


def test_appends_fail_suffix_without_doubling_the_slash():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    ping_monitor("https://hc-ping.example/uuid", suffix="/fail", transport=transport)
    ping_monitor("https://hc-ping.example/uuid/", suffix="/fail", transport=transport)

    assert [str(c.url) for c in calls] == [
        "https://hc-ping.example/uuid/fail",
        "https://hc-ping.example/uuid/fail",
    ]


def test_sends_the_body_when_given():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    ping_monitor(
        "https://hc-ping.example/uuid",
        body="task=garmin_sync error=boom",
        transport=httpx.MockTransport(handler),
    )

    assert calls[0].content == b"task=garmin_sync error=boom"


def test_network_error_does_not_propagate():
    """healthchecks.io fora do ar não pode quebrar o job."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns is down", request=request)

    assert (
        ping_monitor("https://hc-ping.example/uuid", transport=httpx.MockTransport(handler))
        is False
    )


def test_timeout_does_not_propagate():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    assert (
        ping_monitor("https://hc-ping.example/uuid", transport=httpx.MockTransport(handler))
        is False
    )


def test_bad_status_is_false_but_does_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert (
        ping_monitor("https://hc-ping.example/uuid", transport=httpx.MockTransport(handler))
        is False
    )
