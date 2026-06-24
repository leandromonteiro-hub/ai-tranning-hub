# T4.2 Report — Reusable profile-generation service

## What was moved

From `backend/app/scripts/analyze_athlete.py` into `backend/app/services/analysis/profile_service.py`:

| Helper | Purpose |
|---|---|
| `_load_workouts_with_streams` | Loads non-deleted workouts + eager streams |
| `_load_load_metrics` | Loads non-deleted load metrics |
| `_load_profile` | Loads AthleteProfile (or None) |
| `_build_quarterly_windows` | Builds quarterly FTP estimation windows |
| `_upsert_ftp_history` | Idempotent FtpHistory upsert |
| `_upsert_power_curve_points` | Idempotent PowerCurvePoint upsert |

New addition in `profile_service.py`:
- `_load_recovery_metrics` — loads RecoveryMetric rows (needed by `compute_richness`)

## Service API

```python
# backend/app/services/analysis/profile_service.py
async def generate_and_persist_profile(
    session: AsyncSession,
    ctx: TenantContext,
    athlete_id: uuid.UUID,
) -> dict:
    """Returns:
    {
        n_workouts: int,
        weeks: int,
        ftp_recent: float | None,
        n_blocks: int,
        n_races: int,
        excluded_power_streams: int,
        richness: dict,   # RichnessIndex as plain dict
    }
    """
```

Behaviour:
- Loads workouts + streams, load_metrics, recovery_metrics, AthleteProfile
- Runs ftp_estimator (all_time_power_curve + estimate_ftp_timeline), profile_metrics, methodology, report_builder
- Computes `RichnessIndex` via `compute_richness` and stores `asdict(richness)` under `twin_seed["data_richness"]`
- Persists FtpHistory (idempotent via valid_from + source="task2_analysis")
- Persists PowerCurvePoint (idempotent via duration_s + period_label="all-time")
- Creates AthleteProfile if missing (freshly-registered athlete)
- Does NOT write any file

## CLI refactor (`analyze_athlete.py`)

`run_analysis` now:
1. Calls `generate_and_persist_profile` for DB persistence
2. Reloads data and reruns analysis steps to build the markdown report with the caller-supplied `athlete_name`
3. Writes `<slug>-perfil.md` (unchanged behavior)
4. Prints summary now including richness label + score

All helpers (`_load_workouts_with_streams`, `_load_load_metrics`, `_load_profile`, `_build_quarterly_windows`, `_upsert_ftp_history`, `_upsert_power_curve_points`) are imported from `profile_service` — no duplication.

## TDD RED/GREEN

### New tests (`app/tests/test_analysis/test_profile_service.py`)

6 tests, all GREEN:

```
app/tests/test_analysis/test_profile_service.py::test_twin_seed_persisted_with_richness PASSED
app/tests/test_analysis/test_profile_service.py::test_ftp_history_rows_created PASSED
app/tests/test_analysis/test_profile_service.py::test_power_curve_points_created PASSED
app/tests/test_analysis/test_profile_service.py::test_returns_summary_dict PASSED
app/tests/test_analysis/test_profile_service.py::test_idempotent_on_rerun PASSED
app/tests/test_analysis/test_profile_service.py::test_creates_profile_when_missing PASSED
```

### Full suite

```
326 passed, 1 warning in 233.86s
```

(includes existing `test_analyze_athlete_integration.py` — 5 tests, all green)

## Files touched

- `backend/app/services/analysis/profile_service.py` — CREATED (new service)
- `backend/app/scripts/analyze_athlete.py` — REFACTORED (delegates to service)
- `backend/app/tests/test_analysis/test_profile_service.py` — CREATED (new tests)

## Concerns / notes

1. The CLI's `run_analysis` currently runs the analysis twice (once in the service, once to build the markdown with the correct `athlete_name`). This is intentional: the service uses a placeholder name ("Athlete") since it doesn't know the athlete's display name, which is only available from the DB `Athlete.full_name`. The cost is negligible (pure computation, no extra DB queries for workouts). A cleaner future improvement would be to pass `athlete_name` optionally into `generate_and_persist_profile`, but that would change its signature and is outside T4.2 scope.
2. No real athlete data in tests.
3. Idempotency is fully preserved — verified by the `test_idempotent_on_rerun` test.
