# Task 1 — TrainingPeaks Export Ingestion Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) tracking.

**Goal:** Ingest a TrainingPeaks athlete export folder (Metrics + Workout + WorkoutFile zips) into the existing data model — idempotently, multi-tenant scoped, with a quality/ingestion report and a CLI.

**Architecture:** A new folder-level orchestrator (`tp_export_importer`) unzips the 6 export zips to a temp workspace, then: (a) parses `metrics.csv` (long format) into recovery/subjective daily metrics, (b) parses `workouts.csv` (wide format) into planned + completed workouts, (c) feeds each raw activity file (`.fit/.tcx/.gpx`, gunzipped) through the existing `import_file` orchestrator for streams. Reuses existing `NormalizedActivity`, `import_file`, dedup-by-content-hash, and `recompute_load_metrics`.

**Tech Stack:** Python 3.12, FastAPI/SQLAlchemy async, Alembic, pandas, pytest. Backend test cmd (repo root): `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -v"`.

## Global Constraints (from prompt-02)

- **Não comitar dados reais** — `docs/data-atletas/` já está no `.gitignore`. Tests use tiny synthetic/anonymized samples only.
- **Separar dado real × inferido × conhecimento.** `source="trainingpeaks_export"` em todo registro importado. CTL/ATL/TSB são **derivados** (computados por `recompute_load_metrics`), nunca importados como dado real.
- **Idempotente:** rodar 2× não duplica. Dedup nível-arquivo por `content_hash` (já existe em `import_file`); workouts.csv/metrics.csv dedupados por chave natural (athlete+date+...).
- **Multi-tenant:** tudo via `ctx.athlete_id`/`TenantContext`.
- **Código em inglês; relatório do atleta em português.**
- **Real metrics.csv (formato longo)** — colunas `Timestamp,Type,Value`. Tipos presentes neste export: `HRV, Pulse, Sleep Hours, Number Times Woken, Time In {REM,Light,Deep} Sleep, Time Awake, Notes`. **Não há** peso, fadiga, soreness, humor, CTL/ATL/TSB. Detectar tipos dinamicamente (case-insensitive); ignorar tipos não mapeados e reportá-los.
- **Real workouts.csv (formato largo)** — colunas: `Title, WorkoutType, WorkoutDescription, PlannedDuration (h), PlannedDistanceInMeters, WorkoutDay (YYYY-MM-DD), CoachComments, DistanceInMeters, PowerAverage, PowerMax, Energy (kJ), AthleteComments, TimeTotalInHours, VelocityAverage, VelocityMax, CadenceAverage, CadenceMax, HeartRateAverage, HeartRateMax, TorqueAverage, TorqueMax, IF, TSS, HRZone1..10Minutes, PWRZone1..10Minutes, Rpe, Feeling`. Campos com aspas escapadas (`""`) e **quebras de linha dentro de campos** → usar `pandas.read_csv`/`csv` (nunca split manual). `WorkoutType` ∈ {Bike, MTB, Swim, Strength, Day Off}.

## Design decisions (justified)

- **Model change (additive, minimal):** add nullable JSONB `extra` to `workouts_completed` and `workouts_planned`. Holds TP-specific rich fields the Task-2 analysis needs without column sprawl: `hr_zone_minutes` (list[10]), `pwr_zone_minutes` (list[10]), `power_max`, `velocity_avg`, `velocity_max`, `torque_avg`, `torque_max`, `rpe`, `feeling`, `coach_comments`, `athlete_comments`. `notes` holds `WorkoutDescription`.
- **Modality vs intensity:** CSV `WorkoutType` is modality → maps to `sport` (`Bike`/`MTB`→`cycling`, `Swim`→`swim`, `Strength`→`strength`). Our `WorkoutType` enum is intensity → `classify_workout_type(IF)` when executed, else `OTHER`.
- **metrics.csv mapping:** `HRV→recovery.hrv_ms`, `Pulse→recovery.resting_hr` (daily **min**, rounded — RHR is the resting/lowest reading), `Sleep Hours→recovery.sleep_hours`, `Notes→subjective.comment`. All `source="trainingpeaks_export"`. Unmapped types reported, not stored.
- **planned vs completed:** a row with any executed signal (TimeTotalInHours/TSS/PowerAverage/DistanceInMeters present) → `WorkoutCompleted`; a row with planned signal (PlannedDuration/PlannedDistanceInMeters/WorkoutDescription) → `WorkoutPlanned`. A row may yield both. `Day Off` → counted as rest, not persisted.
- **started_at:** `WorkoutDay` is date-only → `started_at = datetime(date, 00:00)`. Dedup of summary-vs-rawfile by (athlete, workout_date, duration_s rounded to minute).

---

### Sub-task ST1: Add `extra` JSONB to workout tables (model + migration 0005)

**Files:**
- Modify: `backend/app/models/workout.py` (`WorkoutCompleted`, `WorkoutPlanned`)
- Create: `backend/alembic/versions/0005_workout_extra_jsonb.py`
- Test: `backend/app/tests/test_api/test_workout_extra.py` (new)

**Interfaces:**
- Produces: `WorkoutCompleted.extra: dict | None`, `WorkoutPlanned.extra: dict | None` (jsonb).

- [ ] **Step 1: Failing test** — `backend/app/tests/test_api/test_workout_extra.py`: create an in-memory sqlite session (mirror the fixture in `backend/app/tests/test_api/test_anamnese.py`), insert a `WorkoutCompleted` with `extra={"rpe": 7, "pwr_zone_minutes": [10,5]}` and a `WorkoutPlanned` with `extra={"coach_comments": "Z2"}`, commit, re-query, assert the dicts round-trip. (Use `jsonb()` from `app.models.types` — already imported in `workout.py`.)

- [ ] **Step 2: Run → FAIL** (`extra` attribute doesn't exist). Cmd: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_workout_extra.py -v"`

- [ ] **Step 3: Add the column to both models** — in `backend/app/models/workout.py`, add to `WorkoutCompleted` (after `notes`) and `WorkoutPlanned` (after `description`):
```python
    extra: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)
```

- [ ] **Step 4: Migration 0005** — `backend/alembic/versions/0005_workout_extra_jsonb.py` (mirror 0004's style; use `app.models.types.jsonb` column type via `sa`):
```python
"""Add extra JSONB to workout tables for source-specific rich fields.

Revision ID: 0005
Revises: 0004
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("workouts_completed", "workouts_planned"):
        op.add_column(table, sa.Column("extra", JSONB(), nullable=True))


def downgrade() -> None:
    for table in ("workouts_completed", "workouts_planned"):
        op.drop_column(table, "extra")
```
(Confirm `app.models.types.jsonb()` resolves to JSONB on Postgres / JSON on sqlite — match what 0001 used for `ImportedFile.meta`; if the project wraps it, follow that pattern instead of importing JSONB directly.)

- [ ] **Step 5: Run test + suite → PASS.** Cmd: `... python -m pytest app/tests/test_api/test_workout_extra.py -v && python -m pytest -q`

- [ ] **Step 6: Commit** — `git add backend/app/models/workout.py backend/alembic/versions/0005_workout_extra_jsonb.py backend/app/tests/test_api/test_workout_extra.py && git commit -m "feat(workout): add extra JSONB column for source-specific fields (+migration 0005)"`

---

### Sub-task ST2: TrainingPeaks metrics.csv parser (long format)

**Files:**
- Create: `backend/app/services/ingestion/tp_metrics.py`
- Test: `backend/app/tests/test_ingestion/test_tp_metrics.py`

**Interfaces:**
- Produces: `@dataclass TpDailyMetric { metric_date: date; hrv_ms: float|None; resting_hr: int|None; sleep_hours: float|None; comment: str|None }`; `parse_tp_metrics(data: bytes) -> tuple[list[TpDailyMetric], dict]` where the dict is `{"unmapped_types": {type: count}, "rows": n}`.

- [ ] **Step 1: Failing test** — `backend/app/tests/test_ingestion/test_tp_metrics.py`: build a small in-memory CSV (header `"Timestamp","Type","Value"`) with rows across two dates: HRV, two `Pulse` values same day (e.g. 52 and 60 → expect resting_hr 52 = min), `Sleep Hours` 7.5, `Notes` "ok", and one unmapped type `Time Awake`. Assert: two `TpDailyMetric` produced; day-1 has hrv/resting_hr=52/sleep_hours/comment set; report `unmapped_types` contains `Time Awake: 1`.

- [ ] **Step 2: Run → FAIL** (`app.services.ingestion.tp_metrics` missing). Cmd: `... python -m pytest app/tests/test_ingestion/test_tp_metrics.py -v`

- [ ] **Step 3: Implement** — `tp_metrics.py`: read with `pandas.read_csv(io.BytesIO(data))`; group by `Timestamp`→date; map types case-insensitively: `hrv`→hrv_ms (float), `pulse`→collect→resting_hr=round(min), `sleep hours`→sleep_hours (float), `notes`→comment (first non-empty). Collect any other Type into `unmapped_types` counter. Robust float parse (ignore non-numeric). Return list sorted by date + report dict.

- [ ] **Step 4: Run test → PASS.** Cmd as Step 2.

- [ ] **Step 5: Commit** — `git add backend/app/services/ingestion/tp_metrics.py backend/app/tests/test_ingestion/test_tp_metrics.py && git commit -m "feat(ingestion): TrainingPeaks metrics.csv parser (long format → daily metrics)"`

---

### Sub-task ST3: TrainingPeaks workouts.csv parser (wide format)

**Files:**
- Create: `backend/app/services/ingestion/tp_workouts.py`
- Test: `backend/app/tests/test_ingestion/test_tp_workouts.py`

**Interfaces:**
- Consumes: `NormalizedActivity`, `classify_workout_type` (from `normalizer`), `WorkoutType`.
- Produces: `@dataclass TpPlanned { planned_date: date; name: str; sport: str; workout_type: WorkoutType; planned_duration_s: int|None; planned_tss: float|None; description: str|None; extra: dict }`; `parse_tp_workouts(data: bytes) -> tuple[list[NormalizedActivity], list[TpPlanned], dict]`. The report dict: `{"rows": n, "completed": c, "planned": p, "rest_days": r}`. Completed activities carry the rich fields in `NormalizedActivity.notes` (= WorkoutDescription) and an `extra` dict — extend `NormalizedActivity` with `extra: dict = field(default_factory=dict)`.

- [ ] **Step 1 (prep): extend NormalizedActivity** — add `extra: dict = field(default_factory=dict)` to `NormalizedActivity` in `normalizer.py` (additive, defaulted; existing importers unaffected). Thread it into `_persist_activity` in `ingestion_service.py`: set `extra=act.extra or None` on the `WorkoutCompleted(...)` (depends on ST1's column). 

- [ ] **Step 2: Failing test** — `test_tp_workouts.py`: synthetic CSV (use `pandas.DataFrame(...).to_csv`) with: (a) a completed Bike row (WorkoutDay, TimeTotalInHours=1.5, TSS=70, IF=0.8, PowerAverage=200, PowerMax=600, HeartRateAverage=140, PWRZone2Minutes=40, CoachComments="Z2", AthleteComments="senti bem", WorkoutDescription="desc"); (b) a planned-only row (PlannedDuration=2.0, WorkoutDescription="base", no executed fields); (c) a "Day Off" row. Assert: 1 NormalizedActivity (sport=cycling, workout_type from IF=0.8→TEMPO, duration_s=5400, avg_power=200, extra has power_max=600, pwr_zone_minutes index, coach/athlete comments, notes="desc"); 1 TpPlanned (planned_duration_s=7200, description="base"); report rest_days=1.

- [ ] **Step 3: Run → FAIL.** Cmd: `... python -m pytest app/tests/test_ingestion/test_tp_workouts.py -v`

- [ ] **Step 4: Implement** — `tp_workouts.py`: `pandas.read_csv`. Per row: resolve columns case-insensitively (reuse the alias approach from `csv_importer._build_index` or a local map). Determine executed-signal vs planned-signal vs rest (`WorkoutType=="Day Off"`). Build `NormalizedActivity` for completed (started_at = WorkoutDay@00:00, sport from modality map, workout_type=classify_workout_type(IF), source_tss/source_if, avg_power/avg_hr/max_hr/avg_cadence, distance_m, duration_s=round(TimeTotalInHours*3600), notes=WorkoutDescription, extra={power_max, velocity_avg, velocity_max, torque_avg, torque_max, rpe, feeling, coach_comments, athlete_comments, hr_zone_minutes:[...], pwr_zone_minutes:[...]} dropping None/empty). Build `TpPlanned` for planned. Count rest_days. Return (completed, planned, report).

- [ ] **Step 5: Run test → PASS.**

- [ ] **Step 6: Commit** — `git add backend/app/services/ingestion/tp_workouts.py backend/app/services/ingestion/normalizer.py backend/app/services/ingestion/ingestion_service.py backend/app/tests/test_ingestion/test_tp_workouts.py && git commit -m "feat(ingestion): TrainingPeaks workouts.csv parser (planned + completed, rich extra)"`

---

### Sub-task ST4: Folder orchestrator + CLI + ingestion report

**Files:**
- Create: `backend/app/services/ingestion/tp_export_importer.py`
- Create: `backend/app/scripts/import_athlete.py`
- Modify: `Makefile` (add `import-athlete` target)
- Test: `backend/app/tests/test_ingestion/test_tp_export_importer.py`

**Interfaces:**
- Consumes: `parse_tp_metrics`, `parse_tp_workouts`, `import_file` (for raw activity files), repositories (`RecoveryRepository`, `SubjectiveRepository`, `WorkoutRepository`, planned repo), `recompute_load_metrics`.
- Produces: `@dataclass IngestionReport {...}`; `async def import_athlete_folder(session, ctx, athlete_id, folder: Path, source="trainingpeaks_export") -> IngestionReport`. Idempotent.

- [ ] **Step 1: Failing test** — `test_tp_export_importer.py`: build a tiny fake folder in `tmp_path` with one `TP-2025/` containing a `MetricsExport-*.zip` (metrics.csv: a couple HRV/Sleep rows), a `WorkoutExport-*.zip` (workouts.csv: 1 completed + 1 planned + 1 Day Off), and a `WorkoutFileExport-*.zip` (one tiny `.gpx.gz`). Run `import_athlete_folder` twice with the same in-memory sqlite session/ctx (mirror the anamnese fixture, add FTP). Assert: first run creates N workouts + M recovery days; report fields populated (period covered, counts, power/hrv coverage); **second run creates 0 new** (idempotent) — file-hash dedup + natural-key dedup.

- [ ] **Step 2: Run → FAIL.** Cmd: `... python -m pytest app/tests/test_ingestion/test_tp_export_importer.py -v`

- [ ] **Step 3: Implement** — `tp_export_importer.py`:
  - `unzip` each `*.zip` under the athlete folder to a `tempfile.TemporaryDirectory` (stdlib `zipfile`); never write into the repo.
  - Metrics: find `metrics.csv`, `parse_tp_metrics`, upsert `RecoveryMetric`/`SubjectiveMetric` by (athlete, date) — update-or-insert so re-runs don't duplicate (use the `UniqueConstraint` per-date already on those tables).
  - Workouts: find `workouts.csv`, `parse_tp_workouts`; persist completed via `WorkoutRepository` with natural-key dedup `(athlete, workout_date, duration_s)`; persist planned via the planned repo with dedup `(athlete, planned_date, name)`. Tag `source`.
  - Raw activity files: for each `*.fit.gz/.tcx.gz/.gpx.gz`, gunzip to bytes and call `import_file(session, ctx, athlete_id, <name without .gz>, data, source="trainingpeaks_export")` — its content-hash dedup gives idempotency and its stream parsing fills `workout_streams`. Cross-dedup the summary-CSV workout vs the raw-file workout by `(workout_date, duration_s±60s)` so the same session isn't double-counted (prefer the raw-file row when both exist, since it has streams).
  - After persistence, `recompute_load_metrics`.
  - Build `IngestionReport`: workouts_completed, workouts_planned, rest_days, recovery_days, subjective_days, period (min/max date), pct_power (completed with avg_power/total), pct_hr, pct_hrv (recovery days with hrv/total), unmapped_metric_types, anomalies (e.g. duration>16h, tss>700, negative values), duplicates_skipped.
  - `import_athlete.py`: argparse `--athlete <slug>` (folder `docs/data-atletas/<slug>`), `--email <athlete email>` to resolve the athlete; builds `TenantContext`, calls `import_athlete_folder`, prints the report as readable text + JSON. Mirror `sample_import.py`'s session/ctx setup.
  - Makefile: `import-athlete:` → `$(COMPOSE) exec api python -m app.scripts.import_athlete --athlete $(ATHLETE) --email $(EMAIL)`.

- [ ] **Step 4: Run test → PASS + full suite green.** Cmd: `... python -m pytest app/tests/test_ingestion/test_tp_export_importer.py -v && python -m pytest -q`

- [ ] **Step 5: Commit** — `git add backend/app/services/ingestion/tp_export_importer.py backend/app/scripts/import_athlete.py Makefile backend/app/tests/test_ingestion/test_tp_export_importer.py && git commit -m "feat(ingestion): TrainingPeaks export folder orchestrator + CLI + ingestion report"`

---

### Sub-task ST5 (controller-run): Real ingestion of leandromonteiro

Not a code task. After ST1–ST4 land: rebuild the api image if needed, run the migration, then:
`docker compose exec api python -m app.scripts.import_athlete --athlete leandromonteiro --email <a seeded athlete email>` (or create/resolve a dedicated athlete). Capture the ingestion report, sanity-check counts against the raw CSVs (≈ workouts rows, recovery days), and save the report under `docs/atletas/leandromonteiro-ingestao.md` (gitignored data stays out; the report is aggregate stats only — safe to commit). Verify idempotency by running twice.

## Self-Review (author)
- Coverage: prompt Task-1 items 1–9 → ST4 (unzip temp, parse 3 types, normalize to model, dedup+quality, tenant-scoped, source tag, idempotent, report) + ST2/ST3 (parsers) + ST1 (model fit). CLI + Makefile in ST4. Tests with synthetic samples (no real data) in each ST. `docs/data-atletas/` already gitignored.
- No placeholders. Types consistent: `TpDailyMetric`/`TpPlanned`/`NormalizedActivity.extra`/`IngestionReport`/`import_athlete_folder` defined where produced and consumed.
- Real-format aware: long metrics.csv pivot, wide workouts.csv with multiline-quoted fields via pandas, gz activity files via existing importers.
