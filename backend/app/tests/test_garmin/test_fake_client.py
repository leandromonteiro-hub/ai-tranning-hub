"""FakeGarminClient honra o Protocol e devolve dados configurados."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.services.garmin.client import GarminAuthError
from app.services.garmin.fake_client import FakeGarminClient
from app.services.garmin.types import Connected, NeedsMfa, WellnessSnapshot


def test_login_needs_mfa_then_resume():
    fc = FakeGarminClient(needs_mfa=True)
    res = fc.login("e@x.com", "pw")
    assert isinstance(res, NeedsMfa)
    token = fc.resume_mfa(res.client_state, "123456")
    assert token == {"fake": "token"}


def test_login_direct_when_no_mfa():
    fc = FakeGarminClient(needs_mfa=False)
    res = fc.login("e@x.com", "pw")
    assert isinstance(res, Connected)
    assert res.token == {"fake": "token"}


def test_list_and_download_activity():
    act = WellnessSnapshot(day=date(2026, 6, 30), hrv_ms=60.0, resting_hr=48,
                           sleep_hours=7.5, sleep_score=80.0, body_battery=70.0)
    fc = FakeGarminClient(
        activities=[("act-1", datetime(2026, 6, 30, 6, tzinfo=timezone.utc))],
        fit_bytes=b"FIT-BYTES", wellness={date(2026, 6, 30): act},
    )
    fc.resume({"fake": "token"})
    refs = fc.list_activities(date(2026, 6, 1))
    assert refs[0].activity_id == "act-1"
    assert fc.download_activity_fit("act-1") == b"FIT-BYTES"
    assert fc.get_wellness(date(2026, 6, 30)).hrv_ms == 60.0


def test_auth_error_is_raisable():
    fc = FakeGarminClient(raise_auth_on_resume=True)
    try:
        fc.resume({"fake": "token"})
        assert False, "expected GarminAuthError"
    except GarminAuthError:
        pass


def test_push_and_unschedule_record_calls():
    fc = FakeGarminClient()
    fc.resume({"fake": "token"})
    wid = fc.push_workout({"name": "W"}, date(2026, 7, 1))
    assert wid == "garmin-workout-1"
    assert fc.pushed[0] == ({"name": "W"}, date(2026, 7, 1))
    fc.unschedule_workout(wid)
    assert wid in fc.unscheduled
