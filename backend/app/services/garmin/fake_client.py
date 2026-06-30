"""In-memory GarminClient for tests. No network, no garminconnect import."""
from __future__ import annotations

from datetime import date, datetime

from app.services.garmin.client import GarminAuthError
from app.services.garmin.types import (
    ActivityRef,
    Connected,
    LoginResult,
    NeedsMfa,
    WellnessSnapshot,
)


class FakeGarminClient:
    def __init__(
        self,
        *,
        needs_mfa: bool = False,
        activities: list[tuple[str, datetime]] | None = None,
        fit_bytes: bytes = b"FIT",
        wellness: dict[date, WellnessSnapshot] | None = None,
        raise_auth_on_resume: bool = False,
        raise_auth_on_wellness: bool = False,
    ):
        self._needs_mfa = needs_mfa
        self._activities = activities or []
        self._fit_bytes = fit_bytes
        self._wellness = wellness or {}
        self._raise_auth_on_resume = raise_auth_on_resume
        self._raise_auth_on_wellness = raise_auth_on_wellness
        self._token: dict | None = None
        self.pushed: list[tuple[dict, date]] = []
        self.unscheduled: list[str] = []
        self._workout_seq = 0

    def login(self, email: str, password: str) -> LoginResult:
        if self._needs_mfa:
            return NeedsMfa(client_state={"stage": "mfa", "email": email})
        return Connected(token={"fake": "token"})

    def resume_mfa(self, client_state: dict, mfa_code: str) -> dict:
        return {"fake": "token"}

    def resume(self, token: dict) -> None:
        if self._raise_auth_on_resume:
            raise GarminAuthError("token expired")
        self._token = token

    def list_activities(self, since: date) -> list[ActivityRef]:
        return [
            ActivityRef(activity_id=aid, start_time=ts)
            for aid, ts in self._activities
            if ts.date() >= since
        ]

    def download_activity_fit(self, activity_id: str) -> bytes:
        return self._fit_bytes

    def get_wellness(self, day: date) -> WellnessSnapshot:
        if self._raise_auth_on_wellness:
            raise GarminAuthError("wellness auth failed")
        return self._wellness.get(day, WellnessSnapshot(day=day))

    def push_workout(self, structured_workout: dict, schedule_date: date) -> str:
        self._workout_seq += 1
        wid = f"garmin-workout-{self._workout_seq}"
        self.pushed.append((structured_workout, schedule_date))
        return wid

    def unschedule_workout(self, garmin_workout_id: str) -> None:
        self.unscheduled.append(garmin_workout_id)

    def current_token(self) -> dict | None:
        return self._token
