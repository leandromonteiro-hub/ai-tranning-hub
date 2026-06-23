"""Safety guardrails. MUST run before any LLM recommendation call.

Pure, deterministic, fully testable. Given a snapshot of the athlete's recent
state it returns a risk level, the list of triggered flags and whether the
original recommendation must be blocked in favour of a conservative alternative.

All thresholds are configurable defaults documented in docs/safety_rules.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import RiskLevel


@dataclass(frozen=True)
class SafetyThresholds:
    tsb_critical: float = -30.0          # very negative form -> critical
    tsb_warning: float = -20.0
    ramp_rate_high: float = 8.0          # CTL gain / 7d considered high
    ramp_rate_warning: float = 6.0
    weekly_load_increase_max: float = 0.10  # max +10% week over week
    monotony_high: float = 2.0
    sleep_low_h: float = 6.0
    hrv_drop_pct: float = 0.10           # >10% drop vs baseline
    fatigue_high: int = 4                # subjective 1-5
    consecutive_high_load_days: int = 3
    high_load_tss: float = 120.0


@dataclass
class AthleteSafetySnapshot:
    """Everything the guardrails need. Missing values (None) are skipped, not assumed safe."""

    ctl: float | None = None
    atl: float | None = None
    tsb: float | None = None
    ramp_rate_7d: float | None = None
    monotony: float | None = None
    weekly_tss_current: float | None = None
    weekly_tss_previous: float | None = None
    last_48h_sleep_h: float | None = None
    hrv_recent: float | None = None
    hrv_baseline: float | None = None
    subjective_fatigue: int | None = None
    recent_injury: bool = False
    consecutive_high_load_days: int = 0
    days_to_target_race: int | None = None
    available_minutes_today: int | None = None


@dataclass
class SafetyResult:
    risk_level: RiskLevel
    block_original: bool
    flags: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "risk_level": self.risk_level.value,
            "block_original": self.block_original,
            "flags": self.flags,
        }


def _flag(name: str, severity: str, detail: str) -> dict:
    return {"indicator": name, "severity": severity, "detail": detail}


def evaluate_safety(
    snap: AthleteSafetySnapshot, t: SafetyThresholds | None = None
) -> SafetyResult:
    """Run all guardrail checks and classify overall risk."""
    t = t or SafetyThresholds()
    flags: list[dict] = []

    # TSB (form / readiness)
    if snap.tsb is not None:
        if snap.tsb <= t.tsb_critical:
            flags.append(_flag("tsb", "critical", f"TSB {snap.tsb:.0f} <= {t.tsb_critical}"))
        elif snap.tsb <= t.tsb_warning:
            flags.append(_flag("tsb", "warning", f"TSB {snap.tsb:.0f} <= {t.tsb_warning}"))

    # Ramp rate (fitness build speed)
    if snap.ramp_rate_7d is not None:
        if snap.ramp_rate_7d >= t.ramp_rate_high:
            flags.append(_flag("ramp_rate", "critical", f"CTL ramp {snap.ramp_rate_7d:.1f}/7d"))
        elif snap.ramp_rate_7d >= t.ramp_rate_warning:
            flags.append(_flag("ramp_rate", "warning", f"CTL ramp {snap.ramp_rate_7d:.1f}/7d"))

    # Weekly load increase (the 10% rule)
    if snap.weekly_tss_current and snap.weekly_tss_previous and snap.weekly_tss_previous > 0:
        increase = (snap.weekly_tss_current - snap.weekly_tss_previous) / snap.weekly_tss_previous
        if increase > t.weekly_load_increase_max:
            sev = "critical" if increase > t.weekly_load_increase_max * 2 else "warning"
            flags.append(_flag("weekly_load_increase", sev, f"+{increase*100:.0f}% vs last week"))

    # Monotony
    if snap.monotony is not None and snap.monotony >= t.monotony_high:
        flags.append(_flag("monotony", "warning", f"monotony {snap.monotony:.1f}"))

    # Sleep
    if snap.last_48h_sleep_h is not None and snap.last_48h_sleep_h < t.sleep_low_h:
        flags.append(_flag("sleep", "warning", f"sleep {snap.last_48h_sleep_h:.1f}h < {t.sleep_low_h}h"))

    # HRV drop vs baseline
    if snap.hrv_recent and snap.hrv_baseline and snap.hrv_baseline > 0:
        drop = (snap.hrv_baseline - snap.hrv_recent) / snap.hrv_baseline
        if drop > t.hrv_drop_pct:
            sev = "critical" if drop > t.hrv_drop_pct * 2 else "warning"
            flags.append(_flag("hrv", sev, f"HRV down {drop*100:.0f}% vs baseline"))

    # Subjective fatigue
    if snap.subjective_fatigue is not None and snap.subjective_fatigue >= t.fatigue_high:
        sev = "critical" if snap.subjective_fatigue >= 5 else "warning"
        flags.append(_flag("fatigue", sev, f"reported fatigue {snap.subjective_fatigue}/5"))

    # Recent injury
    if snap.recent_injury:
        flags.append(_flag("injury", "critical", "recent injury reported"))

    # Consecutive high-load days
    if snap.consecutive_high_load_days >= t.consecutive_high_load_days:
        flags.append(
            _flag("consecutive_load", "warning",
                  f"{snap.consecutive_high_load_days} consecutive high-load days")
        )

    return _classify(flags)


def _classify(flags: list[dict]) -> SafetyResult:
    has_critical = any(f["severity"] == "critical" for f in flags)
    warnings = [f for f in flags if f["severity"] == "warning"]

    if has_critical:
        return SafetyResult(RiskLevel.HIGH, block_original=True, flags=flags)
    if len(warnings) >= 1:
        # 1-2 borderline indicators -> moderate, recommend with warning.
        return SafetyResult(RiskLevel.MODERATE, block_original=False, flags=flags)
    return SafetyResult(RiskLevel.LOW, block_original=False, flags=flags)
