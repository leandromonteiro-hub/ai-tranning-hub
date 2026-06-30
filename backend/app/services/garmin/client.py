"""Garmin client interface. The concrete RealGarminClient (Task 5) is the ONLY
place that imports ``garminconnect``. Everything else depends on this Protocol,
so the whole system is testable offline with FakeGarminClient."""
from __future__ import annotations

from datetime import date
from typing import Protocol

from app.services.garmin.types import ActivityRef, LoginResult, WellnessSnapshot


class GarminAuthError(RuntimeError):
    """Auth failed / token invalid (maps to needs_reauth)."""


class GarminSyncError(RuntimeError):
    """A non-auth Garmin call failed (network, parse, rate-limit)."""


class GarminClient(Protocol):
    def login(self, email: str, password: str) -> LoginResult: ...
    def resume_mfa(self, client_state: dict, mfa_code: str) -> dict: ...
    def resume(self, token: dict) -> None: ...
    def list_activities(self, since: date) -> list[ActivityRef]: ...
    def download_activity_fit(self, activity_id: str) -> bytes: ...
    def get_wellness(self, day: date) -> WellnessSnapshot: ...
    def push_workout(self, structured_workout: dict, schedule_date: date) -> str: ...
    def unschedule_workout(self, garmin_workout_id: str) -> None: ...
    def current_token(self) -> dict | None: ...


# --- Concrete adapter (the ONLY garminconnect import in the codebase) --------
# VERIFICATION NOTE: the exact garminconnect 0.3.6 method names
# (login(return_on_mfa=True), get_activities_by_date, download_activity,
# get_hrv_data/get_sleep_data/get_rhr_day/get_body_battery,
# upload_workout/schedule_workout/delete_workout, garth.dumps/loads)
# MUST be checked against the installed lib version before/during pilot (Task 10
# / spec §7). The skeleton below reflects the known API as of 2026-06; adjust
# names if the lib diverges.
from datetime import datetime, timezone  # noqa: E402

from app.services.garmin.types import (  # noqa: E402
    ActivityRef,
    Connected,
    LoginResult,
    NeedsMfa,
    WellnessSnapshot,
)


class RealGarminClient:
    """Adapter over python-garminconnect. Translates lib errors to
    GarminAuthError / GarminSyncError so callers never see lib exceptions."""

    def __init__(self) -> None:
        self._api = None  # garminconnect.Garmin instance, set on login/resume

    def login(self, email: str, password: str) -> LoginResult:
        from garminconnect import Garmin
        from garminconnect import GarminConnectAuthenticationError

        try:
            self._api = Garmin(email=email, password=password, return_on_mfa=True)
            result1, client_state = self._api.login()
        except GarminConnectAuthenticationError as exc:
            raise GarminAuthError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — never leak a raw lib exception
            raise GarminSyncError(f"login failed: {exc}") from exc
        if result1 == "needs_mfa":
            return NeedsMfa(client_state=client_state)
        return Connected(token=self._dump_token())

    def resume_mfa(self, client_state: dict, mfa_code: str) -> dict:
        from garminconnect import GarminConnectAuthenticationError

        if self._api is None:
            from garminconnect import Garmin

            self._api = Garmin(return_on_mfa=True)
        try:
            self._api.resume_login(client_state, mfa_code)
        except GarminConnectAuthenticationError as exc:
            raise GarminAuthError(str(exc)) from exc
        return self._dump_token()

    def resume(self, token: dict) -> None:
        from garminconnect import Garmin

        self._api = Garmin()
        try:
            self._api.garth.loads(token)  # restore serialized garth session
            self._api.garth.refresh_oauth2()  # force-refresh; raises if invalid
        except Exception as exc:  # noqa: BLE001 — any restore failure => reauth
            raise GarminAuthError(f"token restore failed: {exc}") from exc

    def _dump_token(self) -> dict:
        return self._api.garth.dumps()

    def current_token(self) -> dict | None:
        return self._dump_token() if self._api else None

    def list_activities(self, since: date) -> list[ActivityRef]:
        try:
            raw = self._api.get_activities_by_date(since.isoformat(),
                                                   datetime.now(timezone.utc).date().isoformat())
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"list_activities failed: {exc}") from exc
        out = []
        for a in raw:
            ts = datetime.fromisoformat(a["startTimeGMT"].replace(" ", "T")).replace(
                tzinfo=timezone.utc
            )
            out.append(ActivityRef(activity_id=str(a["activityId"]), start_time=ts,
                                    name=a.get("activityName")))
        return out

    def download_activity_fit(self, activity_id: str) -> bytes:
        from garminconnect import Garmin

        try:
            return self._api.download_activity(
                activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
            )
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"download failed: {exc}") from exc

    def get_wellness(self, day: date) -> WellnessSnapshot:
        iso = day.isoformat()
        try:
            hrv = self._api.get_hrv_data(iso) or {}
            sleep = self._api.get_sleep_data(iso) or {}
            rhr = self._api.get_rhr_day(iso) or {}
            bb = self._api.get_body_battery(iso, iso) or []
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"wellness fetch failed: {exc}") from exc
        daily_sleep = sleep.get("dailySleepDTO", {}) if isinstance(sleep, dict) else {}
        sleep_secs = daily_sleep.get("sleepTimeSeconds")
        bb_charged = None
        if bb and isinstance(bb, list):
            charged = [d.get("charged") for d in bb if isinstance(d, dict)]
            bb_charged = max([c for c in charged if c is not None], default=None)
        return WellnessSnapshot(
            day=day,
            hrv_ms=(hrv.get("hrvSummary") or {}).get("lastNightAvg"),
            resting_hr=(rhr.get("allMetrics", {}).get("metricsMap", {})
                        .get("WELLNESS_RESTING_HEART_RATE", [{}])[0].get("value")
                        if rhr else None),
            sleep_hours=(sleep_secs / 3600.0) if sleep_secs else None,
            sleep_score=(daily_sleep.get("sleepScores", {}).get("overall", {})
                         .get("value")),
            body_battery=bb_charged,
        )

    def push_workout(self, structured_workout: dict, schedule_date: date) -> str:
        try:
            created = self._api.upload_workout(structured_workout)
            workout_id = str(created.get("workoutId"))
            self._api.schedule_workout(workout_id, schedule_date.isoformat())
            return workout_id
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"push_workout failed: {exc}") from exc

    def unschedule_workout(self, garmin_workout_id: str) -> None:
        try:
            self._api.delete_workout(garmin_workout_id)
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"unschedule failed: {exc}") from exc
