from app.models.enums import RiskLevel
from app.services.planning import workout_adjuster as wa

_HARD = {
    "name": "VO2 4x4",
    "elements": [
        {"intensity": "warmup", "duration_s": 600,
         "target": {"type": "power_pct_ftp", "low": 0.55, "high": 0.6}},
        {"count": 4, "steps": [
            {"intensity": "active", "duration_s": 240,
             "target": {"type": "power_pct_ftp", "low": 1.15, "high": 1.2}},  # Z5
            {"intensity": "rest", "duration_s": 180,
             "target": {"type": "power_pct_ftp", "low": 0.5, "high": 0.5}},
        ]},
        {"intensity": "cooldown", "duration_s": 300,
         "target": {"type": "power_pct_ftp", "low": 0.5, "high": 0.5}},
    ],
}


def _max_pct(struct):
    out = []
    for el in struct["elements"]:
        steps = el["steps"] if "steps" in el else [el]
        for s in steps:
            hi = (s["target"] or {}).get("high") or (s["target"] or {}).get("low") or 0
            out.append(hi)
    return max(out)


def _active_seconds_local(struct):
    out = 0
    for el in struct["elements"]:
        for s in (el.get("steps") or [el]):
            if s.get("intensity") == "active":
                out += s.get("duration_s", 0)
    return out


def test_high_risk_becomes_recovery():
    r = wa.adjust(_HARD, RiskLevel.HIGH)
    assert r.changed is True
    assert _max_pct(r.adjusted_structure) <= 0.75  # sem intensidade
    assert r.change_summary["risk"] == "HIGH"


def test_moderate_caps_intensity_and_trims_volume():
    r = wa.adjust(_HARD, RiskLevel.MODERATE)
    assert r.changed is True
    assert _max_pct(r.adjusted_structure) <= 1.05  # teto Z4
    # volume dos blocos 'active' reduzido
    before = sum(s["duration_s"] for el in _HARD["elements"]
                 for s in (el.get("steps") or [el]) if s["intensity"] == "active")
    after = sum(s["duration_s"] for el in r.adjusted_structure["elements"]
                for s in (el.get("steps") or [el]) if s["intensity"] == "active")
    assert after < before


def test_low_risk_keeps_plan_unchanged():
    r = wa.adjust(_HARD, RiskLevel.LOW)
    assert r.changed is False
    assert r.adjusted_structure == _HARD


def test_moderate_intensity_ceiling_holds_on_reapplication():
    once = wa.adjust(_HARD, RiskLevel.MODERATE).adjusted_structure
    twice = wa.adjust(once, RiskLevel.MODERATE).adjusted_structure
    assert _max_pct(twice) <= 1.05  # capear de novo não estoura o teto
    # scale_volume compõe: reaplicar MODERATE reduz a duração de novo (não-idempotente)
    assert _active_seconds_local(twice) < _active_seconds_local(once)


def test_none_structure_is_safe():
    r = wa.adjust(None, RiskLevel.HIGH)
    assert r.changed is False
    assert r.adjusted_structure == {"elements": []}
