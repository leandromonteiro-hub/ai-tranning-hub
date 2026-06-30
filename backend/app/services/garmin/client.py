"""Garmin client interface. The concrete RealGarminClient (Task 5) is the ONLY
place that imports ``garminconnect``. Everything else depends on this Protocol,
so the whole system is testable offline with FakeGarminClient."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol

from app.services.garmin.types import (
    ActivityRef,
    Connected,
    LoginResult,
    NeedsMfa,
    WellnessSnapshot,
)


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
# VERIFICATION NOTE (2026-06-30, garminconnect 0.3.6 introspection):
# Method NAMES are now verified:
#   login(return_on_mfa=True), resume_login, get_activities_by_date,
#   download_activity(dl_fmt=ActivityDownloadFormat.ORIGINAL),
#   get_hrv_data, get_sleep_data, get_rhr_day, get_body_battery,
#   upload_workout, schedule_workout, unschedule_workout, get_full_name,
#   garmin.client.dumps() / garmin.client.loads(tokenstore: str).
# There is NO garth attribute and NO refresh_oauth2 / delete_workout.
# The token object is garmin.client (garminconnect.client.Client).
#
# RESIDUAL pilot-gate items (response-body shapes, unverified against a live account):
#   - schedule_workout() response: key for the scheduled-workout id
#     (tried: workoutScheduleId, scheduleId, id; falls back to workoutId).
#   - get_hrv_data(): hrvSummary.lastNightAvg field path.
#   - get_sleep_data(): dailySleepDTO.* field paths.
#   - get_rhr_day(): allMetrics.metricsMap.WELLNESS_RESTING_HEART_RATE path.
#   - get_body_battery(): list-of-dicts with "charged" key.
# Confirm these during first pilot run against a real Garmin account.


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
            raise GarminAuthError(f"login failed: {exc}") from exc
        if result1 == "needs_mfa":
            return NeedsMfa(client_state=client_state)
        return Connected(token=self._dump_token())

    def resume_mfa(self, client_state: dict, mfa_code: str) -> dict:
        from garminconnect import Garmin, GarminConnectAuthenticationError

        try:
            if self._api is None:
                self._api = Garmin(return_on_mfa=True)
            self._api.resume_login(client_state, mfa_code)
        except GarminConnectAuthenticationError as exc:
            raise GarminAuthError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — never leak a raw lib exception
            raise GarminAuthError(f"resume_mfa failed: {exc}") from exc
        return self._dump_token()

    def resume(self, token: dict) -> None:
        from garminconnect import Garmin

        try:
            self._api = Garmin()
            self._api.client.loads(token["tokenstore"])
            # No explicit refresh in 0.3.6 — validate with a cheap authed call so an
            # expired/invalid token surfaces now as GarminAuthError (→ needs_reauth).
            self._api.get_full_name()
        except Exception as exc:  # noqa: BLE001 — any restore/validate failure => reauth
            raise GarminAuthError(f"token restore failed: {exc}") from exc

    def _dump_token(self) -> dict:
        try:
            return {"tokenstore": self._api.client.dumps()}
        except Exception as exc:  # noqa: BLE001
            raise GarminAuthError(f"token dump failed: {exc}") from exc

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
            workout_id = created.get("workoutId")
            scheduled = self._api.schedule_workout(workout_id, schedule_date.isoformat())
            # The scheduled-workout id (needed to unschedule) lives in the schedule
            # response. Field name not yet verified against a live account — try the
            # common keys, fall back to workout_id. PILOT: confirm the real key.
            sched_id = None
            if isinstance(scheduled, dict):
                for k in ("workoutScheduleId", "scheduleId", "id"):
                    if scheduled.get(k) is not None:
                        sched_id = scheduled[k]
                        break
            return str(sched_id if sched_id is not None else workout_id)
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"push_workout failed: {exc}") from exc

    def unschedule_workout(self, garmin_workout_id: str) -> None:
        try:
            self._api.unschedule_workout(garmin_workout_id)
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"unschedule failed: {exc}") from exc
