"""Client determinístico da Whoop para teste offline.

Mesma razão do fake_client do Garmin: o sync inteiro precisa ser testável sem
rede e sem conta real.
"""
from __future__ import annotations

from datetime import date

from app.services.whoop.types import WhoopDay


class FakeWhoopClient:
    def __init__(self, days: list[WhoopDay], *, raise_on_fetch: Exception | None = None) -> None:
        self._days = days
        self._raise = raise_on_fetch
        self.calls: list[tuple[date, date]] = []
        self.token = {
            "access_token": "fake",
            "refresh_token": "fake",
            "expires_at": 9_999_999_999,
        }

    def fetch_days(self, start: date, end: date) -> list[WhoopDay]:
        self.calls.append((start, end))
        if self._raise is not None:
            raise self._raise
        return [d for d in self._days if start <= d.metric_date <= end]
