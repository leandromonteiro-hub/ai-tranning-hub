"""Garmin pilot smoke-test — validate the residual response-body shapes against a REAL account.

This is a one-off diagnostic for the pilot onboarding. It talks to garminconnect
DIRECTLY (raw) on purpose: the goal is to PRINT the real response shapes so we can
confirm (or fix) the field paths that `RealGarminClient` parses — the only items left
on the spec's pilot gate (§7). It also round-trips the token and exercises a real
push + unschedule.

⚠️  It uses a REAL Garmin account and will:
      - create a workout in the library and SCHEDULE it for tomorrow,
      - then UNSCHEDULE and DELETE it (cleanup) at the end.
    Nothing else is modified. Read-only for activities/wellness.

Run (no Python on host → use the backend Docker image, interactive for the MFA code):

    docker run --rm -it -v "$(pwd -W)/backend":/app \
      -e GARMIN_EMAIL="you@example.com" -e GARMIN_PASSWORD="..." \
      aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m app.scripts.garmin_pilot_smoke"

Optional env: GARMIN_TEST_DATE=YYYY-MM-DD (wellness day; default = yesterday).

The SUMMARY at the end lists which field paths resolved. If any show MISSING, copy the
printed raw shape and we adjust `RealGarminClient` accordingly.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

from app.models.enums import BlockType, RiskLevel
from app.services.garmin.workout_translator import to_garmin_workout
from app.services.workout.builder import build_for


def _j(obj, limit: int = 1600) -> str:
    s = json.dumps(obj, indent=2, default=str, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "\n  …(truncated)…"


def _hdr(title: str) -> None:
    print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)


def main() -> int:
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        print("Set GARMIN_EMAIL and GARMIN_PASSWORD env vars.")
        return 2
    test_day = os.getenv("GARMIN_TEST_DATE") or (date.today() - timedelta(days=1)).isoformat()

    from garminconnect import Garmin

    summary: dict[str, str] = {}

    # --- 1. Login (interactive MFA) -------------------------------------------------
    _hdr("1. LOGIN (MFA interativo)")
    api = Garmin(email=email, password=password, prompt_mfa=lambda: input("  MFA code: ").strip())
    api.login()
    print("  login OK — full name:", api.get_full_name())
    summary["login"] = "OK"

    # --- 2. Token round-trip (client.dumps/loads) -----------------------------------
    _hdr("2. TOKEN round-trip (client.dumps -> loads -> get_full_name)")
    token_str = api.client.dumps()
    print(f"  client.dumps() -> str of len {len(token_str)}")
    api2 = Garmin()
    api2.client.loads(token_str)
    print("  restored OK — full name:", api2.get_full_name())
    summary["token_dumps_loads"] = "OK"

    # --- 3. Wellness shapes (the residual gate) -------------------------------------
    _hdr(f"3. WELLNESS shapes para {test_day}")
    hrv = api.get_hrv_data(test_day) or {}
    sleep = api.get_sleep_data(test_day) or {}
    rhr = api.get_rhr_day(test_day) or {}
    bb = api.get_body_battery(test_day, test_day) or []
    print("  -- get_hrv_data raw --\n", _j(hrv))
    print("  -- get_sleep_data raw --\n", _j(sleep))
    print("  -- get_rhr_day raw --\n", _j(rhr))
    print("  -- get_body_battery raw --\n", _j(bb))

    # What RealGarminClient extracts today (mirror its parsing):
    daily_sleep = sleep.get("dailySleepDTO", {}) if isinstance(sleep, dict) else {}
    sleep_secs = daily_sleep.get("sleepTimeSeconds")
    bb_charged = None
    if bb and isinstance(bb, list):
        charged = [d.get("charged") for d in bb if isinstance(d, dict)]
        bb_charged = max([c for c in charged if c is not None], default=None)
    extracted = {
        "hrv_ms (hrvSummary.lastNightAvg)": (hrv.get("hrvSummary") or {}).get("lastNightAvg"),
        "resting_hr (allMetrics.metricsMap.WELLNESS_RESTING_HEART_RATE[0].value)": (
            rhr.get("allMetrics", {}).get("metricsMap", {})
            .get("WELLNESS_RESTING_HEART_RATE", [{}])[0].get("value") if rhr else None
        ),
        "sleep_hours (dailySleepDTO.sleepTimeSeconds/3600)": (sleep_secs / 3600.0) if sleep_secs else None,
        "sleep_score (dailySleepDTO.sleepScores.overall.value)": (
            daily_sleep.get("sleepScores", {}).get("overall", {}).get("value")
        ),
        "body_battery (max charged)": bb_charged,
    }
    print("\n  -- VALUES RealGarminClient would extract --")
    for k, v in extracted.items():
        status = "MISSING/None" if v is None else "OK"
        print(f"    [{status:13}] {k} = {v!r}")
        summary[f"wellness:{k.split(' ')[0]}"] = status

    # --- 4. Activities ---------------------------------------------------------------
    _hdr("4. ACTIVITIES (list últimos 7 dias + download 1 FIT ORIGINAL)")
    start = (date.today() - timedelta(days=7)).isoformat()
    acts = api.get_activities_by_date(start, date.today().isoformat()) or []
    print(f"  {len(acts)} atividades no período")
    if acts:
        a0 = acts[0]
        print("  primeira atividade (campos-chave):",
              _j({k: a0.get(k) for k in ("activityId", "activityName", "startTimeGMT")}))
        data = api.download_activity(a0["activityId"], dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
        print(f"  download_activity ORIGINAL -> {len(data)} bytes (header: {data[:12]!r})")
        summary["activities"] = f"OK ({len(acts)} found)"
    else:
        summary["activities"] = "no activities in last 7d"

    # --- 5. Push + schedule + unschedule (find the real scheduled-id key) ------------
    _hdr("5. PUSH workout -> schedule (amanhã) -> unschedule (cleanup)")
    sw = build_for(BlockType.BASE, RiskLevel.LOW, 250.0)  # sample endurance
    payload = to_garmin_workout(sw)
    created = api.upload_workout(payload)
    print("  -- upload_workout return --\n", _j(created))
    workout_id = created.get("workoutId") if isinstance(created, dict) else None
    print("  workoutId:", workout_id)

    sched_id = None
    if workout_id is not None:
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        scheduled = api.schedule_workout(workout_id, tomorrow)
        print("  -- schedule_workout return (PROCURE a chave do scheduled-id aqui) --\n", _j(scheduled))
        if isinstance(scheduled, dict):
            for k in ("workoutScheduleId", "scheduleId", "id"):
                if scheduled.get(k) is not None:
                    sched_id = scheduled[k]
                    print(f"  >>> scheduled-id detectado na chave '{k}': {sched_id}")
                    summary["schedule_id_key"] = k
                    break
            if sched_id is None:
                print("  >>> NENHUMA das chaves testadas (workoutScheduleId/scheduleId/id) — "
                      "veja o raw acima e me diga a chave certa.")
                summary["schedule_id_key"] = "UNKNOWN — check raw above"

    # cleanup: unschedule the scheduled instance, then delete the library workout
    try:
        if sched_id is not None:
            api.unschedule_workout(sched_id)
            print("  unschedule_workout OK (agendamento removido)")
            summary["unschedule"] = "OK"
        if workout_id is not None:
            api.delete_workout(workout_id)
            print("  delete_workout OK (workout removido da biblioteca — cleanup)")
    except Exception as exc:  # noqa: BLE001 — cleanup best-effort, report it
        print(f"  ⚠️ cleanup falhou ({exc}) — verifique manualmente no Garmin Connect "
              f"(workoutId={workout_id}, scheduledId={sched_id}).")
        summary["cleanup"] = f"MANUAL ({exc})"

    # --- SUMMARY ---------------------------------------------------------------------
    _hdr("SUMMARY (confirme os shapes; ajuste RealGarminClient se algo der MISSING/UNKNOWN)")
    for k, v in summary.items():
        print(f"  {k:55} {v}")
    print("\n  Itens a confirmar no client.py se divergirem:")
    print("    - schedule_id_key acima (push_workout extrai com fallback)")
    print("    - quaisquer wellness com MISSING/None (get_wellness)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
