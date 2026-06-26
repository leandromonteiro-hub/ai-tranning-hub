"""Deterministic adjustment of a planned workout to current form/risk.

Pure: operates on the JSON dict of a StructuredWorkout, never touches the DB.
Drives off the guardrail RiskLevel (which already accounts for fatigue,
monotony and ramp). The LLM only writes the human-facing justification.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from app.models.enums import RiskLevel

# %FTP ceiling (fraction) per Coggan zone — upper bound, exclusive-ish.
_ZONE_CEIL = {1: 0.55, 2: 0.75, 3: 0.90, 4: 1.05, 5: 1.20, 6: 1.50, 7: 3.0}

_RECOVERY_CEIL = 0.65   # easy Z1-Z2 spin
_MODERATE_MAX_ZONE = 4
_MODERATE_VOLUME_FACTOR = 0.85


@dataclass
class AdjustResult:
    adjusted_structure: dict
    change_summary: dict = field(default_factory=dict)
    changed: bool = False


def _iter_steps(structure: dict):
    for el in structure.get("elements", []):
        if "steps" in el:
            for s in el["steps"]:
                yield s
        else:
            yield el


def _top_pct(structure: dict) -> float:
    vals = []
    for s in _iter_steps(structure):
        t = s.get("target") or {}
        vals.append(t.get("high") or t.get("low") or 0.0)
    return max(vals, default=0.0)


def _active_seconds(structure: dict) -> int:
    return sum(s.get("duration_s", 0) for s in _iter_steps(structure)
               if s.get("intensity") == "active")


def cap_intensity(structure: dict, max_zone: int) -> dict:
    """Clamp any target above max_zone's ceiling down to that ceiling."""
    ceil = _ZONE_CEIL[max_zone]
    out = copy.deepcopy(structure)
    for s in _iter_steps(out):
        t = s.get("target")
        if not t or t.get("type") != "power_pct_ftp":
            continue
        for k in ("low", "high"):
            if t.get(k) is not None and t[k] > ceil:
                t[k] = ceil
    return out


def scale_volume(structure: dict, factor: float) -> dict:
    """Reduce the duration of 'active' steps by `factor` (min 60s)."""
    out = copy.deepcopy(structure)
    for s in _iter_steps(out):
        if s.get("intensity") == "active":
            s["duration_s"] = max(60, round(s.get("duration_s", 0) * factor))
    return out


def to_recovery(structure: dict) -> dict:
    """Replace the workout with a single easy spin derived from its total time,
    capped at 60 min, at a recovery intensity."""
    total = sum(s.get("duration_s", 0) for s in _iter_steps(structure))
    dur = min(total or 1800, 3600)
    name = structure.get("name") or "Treino"
    return {
        "name": f"{name} (recuperação)",
        "sport": structure.get("sport", "cycling"),
        "elements": [
            {"intensity": "active", "duration_s": dur,
             "target": {"type": "power_pct_ftp", "low": 0.5, "high": _RECOVERY_CEIL}},
        ],
    }


def adjust(structure: dict | None, risk_level: RiskLevel) -> AdjustResult:
    if not structure or not structure.get("elements"):
        return AdjustResult(adjusted_structure={"elements": []}, changed=False,
                            change_summary={"risk": risk_level.value, "note": "sem estrutura"})

    before = {"top_pct": round(_top_pct(structure), 2),
              "active_s": _active_seconds(structure)}

    if risk_level == RiskLevel.HIGH:
        adjusted = to_recovery(structure)
    elif risk_level == RiskLevel.MODERATE:
        adjusted = scale_volume(cap_intensity(structure, _MODERATE_MAX_ZONE),
                                _MODERATE_VOLUME_FACTOR)
    else:  # LOW → mantém
        return AdjustResult(adjusted_structure=structure, changed=False,
                            change_summary={"risk": risk_level.value,
                                            "note": "estado alinhado; manter o planejado",
                                            "before": before, "after": before})

    after = {"top_pct": round(_top_pct(adjusted), 2),
             "active_s": _active_seconds(adjusted)}
    changed = adjusted != structure
    return AdjustResult(adjusted_structure=adjusted, changed=changed,
                        change_summary={"risk": risk_level.value,
                                        "before": before, "after": after})
