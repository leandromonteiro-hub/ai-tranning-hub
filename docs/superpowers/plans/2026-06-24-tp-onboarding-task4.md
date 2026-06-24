# Task 4 — Historical-Data Onboarding (TrainingPeaks export) — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Let any athlete bring their TrainingPeaks export: an upload endpoint that triggers the Task-1 ingestion pipeline, auto-generates the Task-2 profile, and computes a per-athlete data-richness index used to calibrate AI recommendation confidence — fully tenant-isolated.

**Architecture:** A pure `data_richness` service; a reusable `profile_service.generate_and_persist_profile` extracted from the Task-2 CLI (DB persistence only, no file write); an onboarding endpoint on the `/imports` router that stages uploaded `.zip`s to a temp dir, runs `import_athlete_folder` (Task 1), then `generate_and_persist_profile` (Task 2 DB seed) + richness, returning a combined response. Guide doc for athletes.

**Tech Stack:** FastAPI/SQLAlchemy async, pytest. Backend test cmd: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -v"`.

## Global Constraints (from prompt-02)

- **Isolamento total multi-tenant:** o histórico de um atleta NUNCA contamina outro nem a base de conhecimento. Tudo via `ctx.athlete_id`. Tests MUST assert athlete A's upload doesn't touch athlete B's rows.
- **Implementar agora APENAS TrainingPeaks export.** Strava/Garmin/Intervals.icu: só citar como design futuro (doc), não implementar.
- **Índice de riqueza de dados** por atleta: anos cobertos, % com potência, % com HRV/sono — usado para calibrar a confiança das recomendações (alinha com o requisito de produto §12.4 da metodologia).
- Não comitar dados reais. Código em inglês; guia do atleta em português.
- Reusar o pipeline da Tarefa 1 (`import_athlete_folder`) e a análise da Tarefa 2 — não duplicar.

## Existing pieces to reuse (verified)
- `app.services.ingestion.tp_export_importer.import_athlete_folder(session, ctx, athlete_id, folder: Path, source) -> IngestionReport` — walks `folder.rglob("*.zip")`, classifies by filename prefix (MetricsExport/WorkoutExport/WorkoutFileExport), so STAGING loose uploaded zips into a temp dir works.
- `app.scripts.analyze_athlete` has the analysis+persistence as module functions: `_load_workouts_with_streams`, `_load_load_metrics`, `_load_profile`, `_build_quarterly_windows`, `_upsert_ftp_history`, `_upsert_power_curve_points`, and uses `ftp_estimator` + `profile_metrics` + `methodology` + `report_builder` to build `twin_seed`. (Extract the DB-persistence orchestration into a service; the CLI keeps the markdown file write.)
- Route pattern: `ctx: TenantContext = Depends(get_tenant)`, `db: AsyncSession = Depends(get_db)`. Add to the existing `/imports` router (`app/api/routes/imports.py`).
- Celery job pattern exists (`app/jobs/import_job.py`) — note as the future async path; this task is synchronous (validation scope: controlled, 2 athletes), matching the "small inline / large async future" convention already in `imports.py`.

## Sub-tasks

### T4.1 — Data-richness index (pure service)
- Create `backend/app/services/analysis/data_richness.py`: `@dataclass RichnessIndex {years_covered: float, n_workouts: int, pct_power: float, pct_hr: float, pct_hrv: float, pct_sleep: float, score: float, label: str}` and `compute_richness(workouts, recovery_days, period_start, period_end) -> RichnessIndex`. `score` in 0..1 from a documented weighted blend (e.g. coverage of power/hrv/sleep + breadth of history capped at ~2 yrs + workout count); `label` ∈ {"baixa","média","alta"} by thresholds. Pure, no DB. TDD with synthetic inputs (full-rich → ~1/"alta"; sparse → low/"baixa").

### T4.2 — Reusable profile-generation service (DB seed, no file)
- Create `backend/app/services/analysis/profile_service.py`: `async def generate_and_persist_profile(session, ctx, athlete_id) -> dict` that loads the athlete's workouts(+streams)/load_metrics/recovery/profile, runs ftp_estimator/profile_metrics/methodology/report_builder to build `twin_seed`, computes `RichnessIndex` (T4.1), persists FtpHistory + PowerCurvePoint + `AthleteProfile.twin_seed` (idempotent, same logic as the Task-2 CLI), stores the richness inside `twin_seed["data_richness"]`, and returns a summary dict (counts, ftp, blocks, races, richness). Refactor `app/scripts/analyze_athlete.py` to call this service for the DB persistence (keep its markdown-file writing in the CLI). Move the reusable `_load_*`/`_upsert_*`/`_build_quarterly_windows` helpers into the service (or import them) — no duplication. TDD against in-memory sqlite (mirror `test_api/test_anamnese.py` fixture; seed athlete + a few workouts/streams/load_metrics/profile), assert twin_seed + richness persisted and idempotent on re-run. Full suite stays green (the CLI still works).

### T4.3 — Onboarding endpoint + schema + tests
- Add to `app/api/routes/imports.py`: `POST /imports/trainingpeaks-export` accepting `files: list[UploadFile]` (the .zip exports), `ctx`/`db` deps. It: writes the uploaded zips into a `tempfile.TemporaryDirectory` (filenames preserved so the orchestrator's prefix classification works), calls `import_athlete_folder(db, ctx, ctx.athlete_id, Path(tmp), source="trainingpeaks_export")`, then `generate_and_persist_profile(db, ctx, ctx.athlete_id)`, commits, and returns a response schema `{ingestion: {...}, richness: {...}, profile: {...}}`. Add the Pydantic response schema. Docstring notes the sync/validation scope + future Celery async path.
- Tests `app/tests/test_api/test_onboarding.py` (mirror anamnese fixture, two athletes A+B): A uploads tiny synthetic TP zips (build in-test with `zipfile`: a metrics.csv + workouts.csv + one .gpx.gz) → assert 200, workouts/recovery created for A, twin_seed + richness present for A; **assert athlete B has ZERO workouts/twin_seed (isolation)**. Assert a second upload is idempotent (no duplication).

### T4.4 — Athlete onboarding guide (doc)
- Create `docs/onboarding-trainingpeaks.md` (Portuguese): step-by-step to export from TrainingPeaks the three exports (Metrics, Workout, WorkoutFile) and upload them; what the system does next (ingest → profile → richness); a short "Formatos futuros" section naming Strava / Garmin / Intervals.icu as planned (design-only, not yet implemented). Committable (no athlete data).

## Self-review
- Covers prompt Task-4: guide (T4.4), upload endpoint triggering pipeline (T4.3), auto-profile after ingest (T4.2 via endpoint), isolation (T4.3 test asserts A≠B), future formats noted not built (T4.4), data-richness index (T4.1) feeding recommendation-confidence calibration (stored in twin_seed). Reuses Task-1/Task-2; no duplication. Sync endpoint w/ documented async-future path.
