"""Garmin client interface. The concrete RealGarminClient (Task 5) is the ONLY
place that imports ``garminconnect``. Everything else depends on this Protocol,
so the whole system is testable offline with FakeGarminClient."""
from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timezone
from typing import Protocol

from app.services.garmin.types import (
    ActivityRef,
    Connected,
    LoginResult,
    NeedsMfa,
    WellnessSnapshot,
)
from app.services.workout.model import Repeat, StructuredWorkout


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
    def push_workout(self, structured_workout: StructuredWorkout, schedule_date: date) -> str: ...
    def unschedule_workout(self, garmin_workout_id: str) -> None: ...
    def current_token(self) -> dict | None: ...


def _build_garmin_workout_dict(sw: StructuredWorkout) -> dict:
    """Build a Garmin workout dict using garminconnect typed builders.

    Produces the correct Garmin API shape with numeric *Id fields that the
    old hand-built translator was missing (sportTypeId, stepTypeId,
    conditionTypeId, workoutTargetTypeId).  All garminconnect imports are
    lazy so this module remains importable without the lib installed.
    """
    from garminconnect.workout import (  # lazy — garminconnect only in client code
        CyclingWorkout,
        TargetType,
        WorkoutSegment,
        create_cooldown_step,
        create_interval_step,
        create_recovery_step,
        create_repeat_group,
        create_warmup_step,
    )

    ftp = sw.ftp_watts
    _counter = [1]  # mutable cell for global step_order

    def _next_order() -> int:
        o = _counter[0]
        _counter[0] += 1
        return o

    def _target_type_and_watts(target):
        """Return (target_type_dict, low_w, high_w). low_w/high_w are None for open targets."""
        if target.type != "power_pct_ftp" or target.low is None or ftp is None:
            return (
                {
                    "workoutTargetTypeId": TargetType.NO_TARGET,
                    "workoutTargetTypeKey": "no.target",
                    "displayOrder": 1,
                },
                None,
                None,
            )
        high = target.high if target.high is not None else target.low
        low_w = round(target.low * ftp)
        high_w = round(high * ftp)
        return (
            {
                "workoutTargetTypeId": TargetType.POWER_ZONE,
                "workoutTargetTypeKey": "power.zone",
                "displayOrder": 1,
            },
            low_w,
            high_w,
        )

    def _make_step(step):
        order = _next_order()
        ttype, low_w, high_w = _target_type_and_watts(step.target)
        intensity = step.intensity
        if intensity == "warmup":
            s = create_warmup_step(step.duration_s, order, ttype)
        elif intensity == "active":
            s = create_interval_step(step.duration_s, order, ttype)
        elif intensity == "rest":
            s = create_recovery_step(step.duration_s, order, ttype)
        else:  # cooldown
            s = create_cooldown_step(step.duration_s, order, ttype)
        # ExecutableStep has extra="allow" — power values attach as extra fields
        if low_w is not None:
            s.targetValueOne = low_w
            s.targetValueTwo = high_w
        return s

    # Compute total duration accounting for repeat multipliers
    total_duration = 0
    for el in sw.elements:
        if isinstance(el, Repeat):
            total_duration += el.count * sum(ch.duration_s for ch in el.steps)
        else:
            total_duration += el.duration_s

    # Build top-level steps (children of a Repeat get orders before the group)
    top_steps = []
    for el in sw.elements:
        if isinstance(el, Repeat):
            children = [_make_step(ch) for ch in el.steps]
            rg = create_repeat_group(el.count, children, _next_order())
            top_steps.append(rg)
        else:
            top_steps.append(_make_step(el))

    workout = CyclingWorkout(
        workoutName=sw.name,
        estimatedDurationInSecs=total_duration,
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2},
                workoutSteps=top_steps,
            )
        ],
    )
    return workout.to_dict()


def _extract_fit_from_original(data: bytes) -> bytes:
    """Unwrap the .fit from Garmin's ORIGINAL download, which is a ZIP archive
    (verified live 2026-07-06). Non-zip bytes pass through unchanged."""
    if not data.startswith(b"PK\x03\x04"):
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        fit = next((n for n in names if n.lower().endswith(".fit")), None)
        if fit is None:
            raise GarminSyncError(f"ORIGINAL zip has no .fit member: {names}")
        return zf.read(fit)


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
# LIVE-ACCOUNT VERIFICATION (2026-07-06, pilot read-only run):
#   - Token dump: client.dumps() OK. Restore MUST be Garmin().login(tokenstore=str)
#     — client.loads() alone skips _load_profile_and_settings(), display_name stays
#     None and every wellness call raises. get_full_name() is a cached attribute
#     (no network), useless as a token health-check.
#   - download_activity(ORIGINAL) returns a ZIP wrapping the .fit (PK header) —
#     unwrapped by _extract_fit_from_original before handing to ingestion.
#   - get_rhr_day(): allMetrics.metricsMap.WELLNESS_RESTING_HEART_RATE[0].value OK.
#   - get_sleep_data()/get_body_battery(): field paths match the live shapes
#     (dailySleepDTO.*, list-of-dicts "charged"); values were null on the probed
#     day (device off overnight) — paths degrade to None as intended.
#   - get_hrv_data(): returned {} on probed day (no HRV recording); path pending
#     a day with real HRV data, degrades to None meanwhile.
#   - schedule_workout() response: scheduled-workout id key CONFIRMED as
#     "workoutScheduleId" (full push→schedule→unschedule cycle exercised live).
# Pilot gate CLOSED — no residual items.


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
            # login(tokenstore=<str>) — NOT client.loads() — is the correct restore
            # path (verified live 2026-07-06): it loads the token, refreshes it when
            # near expiry, and fetches profile/settings, populating display_name,
            # which the wellness endpoint URLs embed. client.loads() alone leaves
            # display_name unset and every wellness call fails. An invalid/expired
            # token surfaces here (profile fetch is a real authed call) => reauth.
            self._api.login(tokenstore=token["tokenstore"])
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
            data = self._api.download_activity(
                activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
            )
        except Exception as exc:  # noqa: BLE001
            raise GarminSyncError(f"download failed: {exc}") from exc
        return _extract_fit_from_original(data)

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

    def push_workout(self, structured_workout: StructuredWorkout, schedule_date: date) -> str:
        try:
            workout_dict = _build_garmin_workout_dict(structured_workout)
            created = self._api.upload_workout(workout_dict)
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
