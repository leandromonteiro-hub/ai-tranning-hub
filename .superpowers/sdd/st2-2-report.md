# ST2.2 Implementation Report — Profile Metrics

## What Was Built

Two new files under `backend/`:

### `backend/app/services/analysis/profile_metrics.py`
Pure module (no DB, no I/O) with four public functions:

| Function | Input | Output |
|---|---|---|
| `weekly_volume_trend(workouts)` | list of workout-like objects | `WeeklyVolumeTrend` |
| `modality_split(workouts)` | list of workout-like objects | `ModalitySplit` |
| `intensity_distribution(workouts)` | list of workout-like objects | `IntensityDistribution` |
| `best_power_marks(power_curve_dict, weight_kg)` | `dict[int,float]`, optional float | `BestPowerMarks` |

### `backend/app/tests/test_analysis/test_profile_metrics.py`
54 tests, 4 test classes, all synthetic inputs.

---

## Return Dataclasses

### WeeklyVolumeTrend
```
WeeklyVolumeTrend
  weeks: list[WeeklyVolumePoint]
    iso_year, iso_week, hours, tss, distance_km, workout_count
  trend: VolumeTrend | None
    mean_hours, mean_tss, direction ("rising"|"falling"|"stable"), weeks_analysed
```
TSS precedence: `extra["source_tss"]` (TP measured) wins over the model's computed `tss` field.

Trend direction: compare second-half mean vs first-half mean of hours; delta < 5 % of overall mean → "stable".

### ModalitySplit
```
ModalitySplit
  by_sport: list[SportShare]         — normalised sport label, count, hours, pct
  by_workout_type: list[WorkoutTypeShare] — workout_type, count, hours, pct
  total_workouts, total_hours
```
Sport normalisation: "Bike", "MTB", "cyclocross", etc. → "cycling"; "swimming"/pool → "swim"; "strength"/"gym"/"weight" → "strength".

### IntensityDistribution
```
IntensityDistribution
  measured: MeasuredZones   (source="trainingpeaks")
    pwr_zone_minutes[0..9], hr_zone_minutes[0..9]
    workouts_with_power_zones, workouts_with_hr_zones
  derived: DerivedZones     (source="derived_if")
    z1_hours, z2_hours, z3_hours, unclassified_hours
    z1_pct, z2_pct, z3_pct
    distribution_label, workouts_classified
```
Measured/derived clearly separated by the `source` field on each sub-dataclass.

### BestPowerMarks
```
BestPowerMarks
  marks: list[PowerMark]
    duration_s, watts, w_per_kg (None if no weight)
  weight_kg: float | None
```
Standard durations: 5 s, 60 s, 300 s, 1200 s, 3600 s. Only durations present in the input dict are returned.

---

## Polarized / Pyramidal / Sweet-Spot Rule (documented in source)

3-zone model (Seiler / polarised framework) from IF:
- Z1 (low):        IF < 0.75
- Z2 (threshold):  0.75 ≤ IF < 0.90
- Z3 (high):       IF ≥ 0.90

Distribution label rules (applied to % of *classifiable hours*, first match wins):
1. **polarized**:   Z1 ≥ 75% AND Z3 ≥ 10% AND Z2 < 20%
2. **sweet_spot**:  Z2 ≥ 35%
3. **pyramidal**:   Z1 > Z2 > Z3 (descending, not polarised, Z2 < 35%)
4. **mixed**:       fallback

These rules are intentionally simple; the label is an approximation for exploratory analysis, not a clinical classification. Full rationale is in the module docstring.

---

## TDD RED/GREEN

### RED phase
Tests were written first for all four functions. Running the test file against a missing module produced:
```
ModuleNotFoundError: No module named 'app.services.analysis.profile_metrics'
```

### GREEN phase
After implementing `profile_metrics.py`, first run:
```
54 collected, 53 passed, 1 FAILED
FAILED test_derived_pct_sum_to_one_when_all_classified
  0.9999 != 1.0 ± 1e-6   (rounding artefact: pcts rounded to 4dp, 1/3 × 3 = 0.9999)
```

Fix: relaxed tolerance to `abs=1e-3` in the test (rounding is intentional; 4dp is sufficient precision for display).

Final run:
```
54 passed, 1 warning in 0.60s
```

---

## Files

- `backend/app/services/analysis/profile_metrics.py` — implementation
- `backend/app/tests/test_analysis/test_profile_metrics.py` — 54 tests

---

## Concerns

1. **`_normalise_sport` heuristic**: The sport normalisation uses keyword matching. New sport strings from future TP exports may need additions. "running" is captured but not merged into cycling as intended by the spec; this is correct behaviour (it's a different modality).
2. **`weight_kg=0` guard**: Zero weight returns `None` for W/kg (division-by-zero protection) — this is explicit and intentional.
3. **Measured zones index alignment**: `extra["pwr_zone_minutes"]` positions map to TP's own zone numbering (which may vary per athlete account). The aggregation is index-faithful — interpretation of which zone index = which power zone is deferred to the report builder (ST2.4).
4. **No FTP used in `intensity_distribution`**: The IF-based 3-zone classification does not require `zones_calculator.power_zones(ftp)` because IF already encodes the FTP-relative intensity. This is simpler and avoids a circular dependency with FTP estimation. The plan note ("Reuse zones_calculator where helpful") was evaluated and the IF approach was chosen as cleaner for per-workout classification.
