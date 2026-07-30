"""Um 429 do Garmin não pode virar pedido de código de verificação.

Incidente real (2026-07-29): o Garmin limitou o IP do servidor por janelas; as
duas estratégias de login rápidas morreram com 429 e o fluxo caiu na estratégia
web. Essa estratégia volta para a tela de login do Garmin, cujo título é
"GARMIN Authentication Application" — e o detector de MFA da biblioteca casa com
"authentication application". A tela pediu um código que o Garmin nunca enviou,
numa conta que nem tem 2FA. O usuário ficou esperando um email inexistente.

O sinal está lá: a própria biblioteca loga "returned 429" antes de cair para a
estratégia web. Estes testes travam a leitura desse sinal.
"""
from __future__ import annotations

import logging

import pytest

from app.services.garmin.client import GarminRateLimited, _saw_rate_limit


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="garminconnect.client", level=logging.WARNING, pathname="", lineno=0,
        msg=msg, args=(), exc_info=None,
    )


def test_detects_the_libs_rate_limit_warning():
    assert _saw_rate_limit([
        _record("mobile+cffi returned 429: Mobile login returned 429 — IP rate limited by Garmin"),
    ]) is True


def test_ignores_unrelated_warnings():
    assert _saw_rate_limit([_record("widget+cffi failed: timeout")]) is False
    assert _saw_rate_limit([]) is False


def test_rate_limited_error_says_what_to_do():
    """A mensagem vai direto para a tela do atleta.

    Ela precisa fazer três coisas, e a segunda é a que resolve o incidente: negar
    explicitamente que exista um código. Só omitir a palavra não basta — o atleta
    vinha de uma tela pedindo código, e o silêncio deixaria a dúvida de pé.
    """
    texto = str(GarminRateLimited()).lower()

    assert "limitando" in texto              # diz o que está acontecendo
    assert "não há código" in texto          # nega o pedido que causou a confusão
    assert "hora" in texto                   # diz quando tentar de novo
    assert "digite" not in texto             # e não pede nada ao atleta


def test_rate_limited_is_an_auth_error():
    """A rota já trata GarminAuthError como 400 com a mensagem — herdar reusa isso."""
    from app.services.garmin.client import GarminAuthError

    assert issubclass(GarminRateLimited, GarminAuthError)
