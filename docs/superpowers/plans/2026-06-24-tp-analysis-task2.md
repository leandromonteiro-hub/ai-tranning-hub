# Task 2 — Athlete Profile & Coach-Methodology Reverse-Engineering — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** From the ingested history (Task 1), compute the athlete's profile, reverse-engineer the previous coach's methodology, and produce a Portuguese report + a 1-page executive summary that earns the athlete's trust, plus seed structured profile data into the DB.

**Architecture:** A read-only analysis service (`profile_analyzer.py`) with pure, testable functions per dimension; a CLI (`analyze_athlete.py`) that runs the analysis for one athlete and (a) writes `docs/atletas/<slug>-perfil.md` + a 1-page executive summary section, and (b) persists structured seed data: estimated `FtpHistory` timeline, `PowerCurvePoint` rows, and a compact JSON "twin seed". Reuses existing `power_curve`, `zones_calculator`, `load_calculator`, `tss_calculator`.

**Tech Stack:** Python 3.12, SQLAlchemy async, pandas, pytest. Backend test cmd: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -v"`.

## Global Constraints (from prompt-02)

- **Separar dado real × inferido.** Cada inferência de metodologia DEVE apontar a evidência no histórico que a sustenta (datas, números). Dado medido vs derivado vs inferido claramente rotulado.
- **Relatório do atleta em português; código em inglês.**
- **Tom:** continuidade inteligente e respeitosa com o treinador anterior; destacar acertos e, com cautela e baseado em evidência, oportunidades — nunca crítica gratuita. **Não prometer resultados**; posicionar como apoio à decisão.
- **Não comitar dados brutos** (`docs/data-atletas/` gitignored); o relatório `docs/atletas/<slug>-perfil.md` contém análise/insights do atleta — tratá-lo como dado do atleta: NÃO commitar (adicionar `docs/atletas/*-perfil.md` ao `.gitignore`); commitar apenas código + testes. (O `-ingestao.md` de stats agregados já foi commitado; o perfil é mais sensível → gitignore.)
- Multi-tenant: tudo via `ctx.athlete_id`.

## Data realities (discovered)

- leandro: 424 completed, 393 planned, 486 recovery days, 340 load_metrics (CTL/ATL/TSB), 391 streams w/ power, **0 FTP rows** → FTP must be ESTIMATED.
- Rich fields live in `WorkoutCompleted.extra`: `pwr_zone_minutes`/`hr_zone_minutes` (TP's own zone split), `coach_comments`, `athlete_comments`, `rpe`, `feeling`, `power_max`. `notes` = WorkoutDescription. `source_tss`/IF available.
- Modalities in `sport` (cycling from Bike/MTB, swim, strength); intensity in `workout_type` (classified from IF).
- Reusable: `power_curve.power_curve(streams)`, `power_curve.best_mean_maximal`, `zones_calculator.power_zones(ftp)`/`hr_zones(max_hr)`, `tss_calculator.normalized_power`, `load_calculator.ramp_rate`.

## Design decisions

- **FTP estimation:** per rolling window (e.g. 90-day), `ftp_est = 0.95 × best_20min_power` from streams in the window; fall back to `best_60min_power` if no 20-min effort. Persist as `FtpHistory(method="estimate_pc20", source="task2_analysis")` rows with `valid_from`/`valid_to` covering each window. Keep it simple: compute quarterly windows over the covered period.
- **Intensity distribution:** prefer TP's `pwr_zone_minutes` from `extra` (the coach's own zones) aggregated; ALSO compute our 3-zone polarized/pyramidal/sweet-spot classification from time-in-zone. Label which is measured (TP) vs derived (ours).
- **Blocks:** detect base/build/peak/taper/recovery from CTL trend + ramp + weekly TSS + TSB using `load_metrics`; a recovery week = local TSS trough / negative ramp; taper = CTL plateau/decline with rising TSB before a race.
- **Races:** detect from `workout_type == RACE`, title keywords (prova/race/maratona/XCO/cup/copa), and TSS/intensity spikes; for each, reconstruct the 2–3 week pre-race CTL/ATL/TSB/volume window.
- **Coach methodology:** aggregate `coach_comments` (term frequency, recurring objectives/structure phrases) — report as evidence-backed observations, not claims.
- **Twin seed (DB):** a compact JSON persisted on `AthleteProfile` via a new nullable jsonb column `twin_seed` (migration 0006) holding: power curve bests, ftp timeline, intensity split, block summary, best performances, data-richness. (Lighter than a new table; YAGNI.)

## Sub-tasks

### ST2.1 — FTP estimation + power-curve persistence
- Create `backend/app/services/analysis/ftp_estimator.py`: `estimate_ftp_timeline(workouts_with_streams, windows) -> list[FtpEstimate{valid_from, valid_to, ftp_watts, method}]` (pure; takes per-window best-20min). Plus `all_time_power_curve(streams) -> dict[int,float]` wrapper over `power_curve`.
- Test with synthetic streams. TDD.

### ST2.2 — Profile metrics (volume, intensity, modality, W/kg)
- Create `backend/app/services/analysis/profile_metrics.py`: pure functions for weekly volume trend (hours/TSS/distance), modality split, intensity distribution (from `extra` zone minutes + our zone classification given an FTP), best power marks (5s/1min/5min/20min/60min from the power curve), W/kg using weight from AthleteProfile (None-safe). TDD synthetic.

### ST2.3 — Methodology reverse-engineering (blocks, taper, races, comments)
- Create `backend/app/services/analysis/methodology.py`: `detect_blocks(load_metrics) -> list[Block{start,end,type,evidence}]`; `detect_races(workouts) -> list[Race]`; `taper_windows(races, load_metrics) -> list[TaperWindow]`; `coach_comment_terms(workouts) -> list[(term,count)]`. Each result carries the evidence (dates/values). TDD synthetic.

### ST2.4 — Report generator + CLI + twin-seed persistence + migration 0006
- Migration 0006: add `twin_seed jsonb` to `athlete_profiles`.
- Create `backend/app/services/analysis/report_builder.py`: assemble the PT-BR markdown (sections: Perfil; Engenharia reversa da metodologia; Metodologia pré-prova; Melhores marcas; Correlação com decisões do treinador; Resumo executivo de 1 página) from the above services, every methodology claim citing evidence.
- Create `backend/app/scripts/analyze_athlete.py`: argparse `--athlete <slug>`/`--email`; loads the athlete's data, runs analysis, writes `docs/atletas/<slug>-perfil.md`, persists FtpHistory + PowerCurvePoint + `AthleteProfile.twin_seed`. Makefile `analyze-athlete` target.
- Test: report builder produces all sections + an evidence citation per methodology claim (synthetic). Idempotent persistence (re-run updates, not duplicates).

### ST2.5 (controller-run) — Run on leandro
- Run `analyze_athlete` for leandro; sanity-check the report; confirm FtpHistory/PowerCurvePoint/twin_seed persisted; verify the report reads coherently and every methodology section cites dates/numbers from his real data.

## Self-review
- Covers prompt Task-2 sections: Perfil (ST2.2), Engenharia reversa (ST2.3), Pré-prova/taper (ST2.3), Melhores marcas (ST2.2+2.3), Correlação/confiança (ST2.3+report), Entregáveis (ST2.4 report+seed+exec summary). Evidence-citation enforced in ST2.3/ST2.4. FTP-estimation gap (0 FTP rows) handled in ST2.1. Profile report gitignored as athlete data.
