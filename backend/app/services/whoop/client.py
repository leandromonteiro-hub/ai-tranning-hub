"""Único módulo que fala HTTP com a Whoop (API oficial v2).

Três regras da API que este módulo encapsula, e cuja violação gravaria lixo como
se fosse medição:

1. **Recovery não tem data.** Ela aponta para o sono por ``sleep_id``; a data sai
   do fim do sono, no fuso do próprio registro (``timezone_offset``).
2. **``nap: true`` é cochilo**, não a noite — somar em sleep_hours infla o sono.
3. **``score_state`` diferente de ``SCORED``** significa score ausente ou
   incompleto: descartar, nunca ler como zero.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.recovery.merge import RecoverySnapshot
from app.services.whoop.types import (
    WhoopAuthError,
    WhoopDay,
    WhoopRateLimited,
    WhoopSyncError,
)

log = get_logger(__name__)

AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
API_BASE = "https://api.prod.whoop.com/developer/v2"
SCOPES = "read:recovery read:sleep offline"
PAGE_LIMIT = 25  # máximo aceito pela API
_TIMEOUT = 20.0
_REFRESH_MARGIN_S = 120  # renova antes de vencer, para não perder a corrida
_MAX_PAGES = 200  # teto de segurança: 200 x 25 = 5000 registros


def authorize_url(state: str, redirect_uri: str) -> str:
    """URL para onde o navegador do atleta é enviado no início do OAuth."""
    return f"{AUTH_URL}?" + urlencode({
        "client_id": settings.whoop_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    })


def _token_request(data: dict, transport: httpx.BaseTransport | None) -> dict:
    payload = {
        **data,
        "client_id": settings.whoop_client_id,
        "client_secret": settings.whoop_client_secret,
    }
    try:
        with httpx.Client(timeout=_TIMEOUT, transport=transport) as c:
            r = c.post(TOKEN_URL, data=payload)
    except Exception as exc:  # noqa: BLE001 — nunca vaza exceção da httpx
        raise WhoopSyncError(f"token request failed: {exc}") from exc
    if r.status_code in (400, 401):
        raise WhoopAuthError(f"token rejeitado pela Whoop ({r.status_code})")
    if r.status_code != 200:
        raise WhoopSyncError(f"token request retornou {r.status_code}")
    body = r.json()
    return {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token", data.get("refresh_token")),
        "expires_at": int(time.time()) + int(body.get("expires_in", 3600)),
    }


class WhoopClient:
    """Chamadas autenticadas à Whoop. Renova o token sozinho quando necessário."""

    def __init__(self, token: dict, *, transport: httpx.BaseTransport | None = None) -> None:
        self._token = dict(token)
        self._transport = transport

    @classmethod
    def exchange_code(
        cls, code: str, redirect_uri: str, *, transport: httpx.BaseTransport | None = None
    ) -> dict:
        """Troca o código do callback pelo par de tokens."""
        return _token_request(
            {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
            transport,
        )

    @property
    def token(self) -> dict:
        return dict(self._token)

    def refresh(self) -> dict:
        self._token = _token_request(
            {"grant_type": "refresh_token", "refresh_token": self._token["refresh_token"]},
            self._transport,
        )
        return self.token

    def _ensure_fresh(self) -> None:
        if self._token.get("expires_at", 0) - _REFRESH_MARGIN_S <= int(time.time()):
            self.refresh()

    def _get(self, path: str, params: dict) -> dict:
        self._ensure_fresh()
        try:
            with httpx.Client(timeout=_TIMEOUT, transport=self._transport) as c:
                r = c.get(
                    f"{API_BASE}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {self._token['access_token']}"},
                )
        except Exception as exc:  # noqa: BLE001
            raise WhoopSyncError(f"GET {path} failed: {exc}") from exc
        if r.status_code == 401:
            raise WhoopAuthError(f"GET {path}: token rejeitado")
        if r.status_code == 429:
            reset = r.headers.get("X-RateLimit-Reset")
            raise WhoopRateLimited(
                f"GET {path}: limite de requisições da Whoop",
                retry_after_s=int(reset) if reset and reset.isdigit() else None,
            )
        if r.status_code != 200:
            raise WhoopSyncError(f"GET {path} retornou {r.status_code}")
        try:
            return r.json()
        except ValueError as exc:
            raise WhoopSyncError(f"GET {path}: corpo não é JSON") from exc

    def _paginate(self, path: str, start: date, end: date) -> list[dict]:
        """Percorre as páginas do recurso na janela [start, end]."""
        records: list[dict] = []
        params = {
            "start": f"{start.isoformat()}T00:00:00.000Z",
            # end é exclusivo na API: +1 dia para incluir o último
            "end": f"{(end + timedelta(days=1)).isoformat()}T00:00:00.000Z",
            "limit": PAGE_LIMIT,
        }
        token: str | None = None
        for _ in range(_MAX_PAGES):
            body = self._get(path, {**params, **({"nextToken": token} if token else {})})
            records.extend(body.get("records") or [])
            token = body.get("next_token")
            if not token:
                return records
        log.warning("whoop: %s excedeu o teto de paginação; truncado", path)
        return records

    def fetch_days(self, start: date, end: date) -> list[WhoopDay]:
        """Sonos e recuperações da janela, casados e resolvidos para data local."""
        sleeps = self._paginate("/activity/sleep", start, end)
        recoveries = self._paginate("/recovery", start, end)

        by_sleep_id: dict[str, tuple[date, dict]] = {}
        for s in sleeps:
            if s.get("nap") or s.get("score_state") != "SCORED":
                continue
            day = _local_wake_date(s)
            if day is None:
                continue
            by_sleep_id[str(s["id"])] = (day, s)

        rec_by_sleep = {
            str(r["sleep_id"]): r
            for r in recoveries
            if r.get("score_state") == "SCORED" and r.get("sleep_id")
        }

        out: list[WhoopDay] = []
        for sleep_id, (day, sleep) in sorted(by_sleep_id.items(), key=lambda kv: kv[1][0]):
            rec = rec_by_sleep.get(sleep_id, {})
            score = rec.get("score") or {}
            out.append(WhoopDay(
                metric_date=day,
                snapshot=RecoverySnapshot(
                    hrv_ms=score.get("hrv_rmssd_milli"),
                    resting_hr=score.get("resting_heart_rate"),
                    recovery_score=score.get("recovery_score"),
                    sleep_hours=_asleep_hours(sleep),
                    sleep_score=(sleep.get("score") or {}).get("sleep_performance_percentage"),
                ),
            ))
        return out


def _local_wake_date(sleep: dict) -> date | None:
    """Data local do fim do sono — o dia cujo treino essa recuperação informa."""
    end, offset = sleep.get("end"), sleep.get("timezone_offset")
    if not end:
        return None
    try:
        dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        if offset:
            sign = -1 if str(offset).startswith("-") else 1
            hh, _, mm = str(offset).lstrip("+-").partition(":")
            dt = dt + sign * timedelta(hours=int(hh), minutes=int(mm or 0))
        return dt.date()
    except (ValueError, TypeError):
        log.warning("whoop: sono com end/offset ilegível: %r / %r", end, offset)
        return None


def _asleep_hours(sleep: dict) -> float | None:
    """Só os estágios dormindo: leve + profundo + REM. Acordado não é sono."""
    stages = ((sleep.get("score") or {}).get("stage_summary")) or {}
    keys = (
        "total_light_sleep_time_milli",
        "total_slow_wave_sleep_time_milli",
        "total_rem_sleep_time_milli",
    )
    values = [stages.get(k) for k in keys]
    if all(v is None for v in values):
        return None
    return round(sum(v or 0 for v in values) / 3_600_000, 2)
