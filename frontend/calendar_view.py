"""Pure helpers + Altair rendering for the weekly training calendar.

Kept separate from app.py so the data-shaping logic (flattening a structured
workout into colored zone segments, classifying Coggan zones, formatting the
interval list, week date math, adherence) is unit-testable without importing
streamlit. Altair is imported lazily inside profile_chart so these pure
functions can be tested in a slim container without the charting stack.
"""
from __future__ import annotations

from datetime import date, timedelta

# Coggan 7-zone model, classified by %FTP (fraction). Fixed categorical palette
# so a zone reads the same color everywhere.
ZONE_NAMES = {
    1: "Recuperação", 2: "Endurance", 3: "Tempo", 4: "Limiar",
    5: "VO2max", 6: "Anaeróbico", 7: "Neuromuscular",
}
ZONE_COLORS = {
    1: "#9e9e9e", 2: "#4a90d9", 3: "#5cb85c", 4: "#f0ad4e",
    5: "#ff8c00", 6: "#d9534f", 7: "#7b2fbe",
}

_OPEN_NOMINAL = 0.45  # easy-spin assumption for an "open"/free segment

_LABEL = {
    "warmup": "Aquecimento", "cooldown": "Volta à calma",
    "active": "Bloco", "rest": "Descanso",
}


def zone_of(pct: float) -> int:
    """Coggan zone for a power target expressed as a fraction of FTP."""
    if pct < 0.56:
        return 1
    if pct < 0.76:
        return 2
    if pct < 0.91:
        return 3
    if pct < 1.06:
        return 4
    if pct < 1.21:
        return 5
    if pct < 1.51:
        return 6
    return 7


def _target_mid(target: dict | None) -> float:
    """Representative %FTP fraction (midpoint) for a step target dict."""
    if not target or target.get("type") != "power_pct_ftp" or target.get("low") is None:
        return _OPEN_NOMINAL
    low = target["low"]
    high = target.get("high")
    high = high if high is not None else low
    return (low + high) / 2


def _segment(step: dict) -> dict:
    pct = _target_mid(step.get("target"))
    return {
        "intensity": step.get("intensity", "active"),
        "duration_s": int(step.get("duration_s", 0)),
        "pct": pct,
        "zone": zone_of(pct),
    }


def flatten_structure(structure: dict | None) -> list[dict]:
    """Expand a StructuredWorkout dict into a flat list of zone segments.

    Each segment: {intensity, duration_s, pct, zone}. Repeat elements are
    expanded `count` times. Empty/malformed input -> [].
    """
    if not structure or not isinstance(structure, dict):
        return []
    out: list[dict] = []
    for el in structure.get("elements", []):
        if "count" in el and "steps" in el:  # Repeat
            for _ in range(int(el["count"])):
                for s in el["steps"]:
                    out.append(_segment(s))
        else:  # Step
            out.append(_segment(el))
    return out


def _pct_text(target: dict | None) -> str:
    if not target or target.get("type") != "power_pct_ftp" or target.get("low") is None:
        return "livre"
    low = target["low"]
    high = target.get("high")
    if high is None or high == low:
        return f"{round(low * 100)}%"
    return f"{round(low * 100)}-{round(high * 100)}%"


def _mins(seconds: int) -> str:
    return f"{round(seconds / 60)}min"


def interval_lines(structure: dict | None) -> list[str]:
    """Human-readable interval breakdown (pt-BR), one line per element."""
    if not structure or not isinstance(structure, dict):
        return []
    lines: list[str] = []
    for el in structure.get("elements", []):
        if "count" in el and "steps" in el:  # Repeat
            steps = el["steps"]
            if len(steps) == 2:
                on, off = steps
                lines.append(
                    f"{el['count']}× {_mins(on['duration_s'])} @ {_pct_text(on.get('target'))}"
                    f" / {_mins(off['duration_s'])} @ {_pct_text(off.get('target'))}"
                )
            else:
                lines.append(f"{el['count']}× bloco:")
                for s in steps:
                    lines.append(f"   · {_mins(s['duration_s'])} @ {_pct_text(s.get('target'))}")
        else:  # Step
            label = _LABEL.get(el.get("intensity", "active"), "Bloco")
            lines.append(f"{label} {_mins(el['duration_s'])} @ {_pct_text(el.get('target'))}")
    return lines


def adherence(plan_tss: float | None, actual_tss: float | None) -> tuple[str, str]:
    """Return (emoji, label) comparing actual vs planned TSS.

    Empty when there is no plan or no actual. Green >=90%, yellow 50-90%,
    red <50%.
    """
    if not plan_tss or actual_tss is None:
        return ("", "")
    ratio = actual_tss / plan_tss
    if ratio >= 0.9:
        emoji = "✅"
    elif ratio >= 0.5:
        emoji = "🟡"
    else:
        emoji = "🔴"
    return (emoji, f"{round(actual_tss)} / {round(plan_tss)} TSS")


def week_dates(anchor: date) -> list[date]:
    """The 7 dates (Mon..Sun) of the ISO week containing `anchor`."""
    monday = anchor - timedelta(days=anchor.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def profile_chart(segments: list[dict], *, mini: bool = True):
    """Stepped power-profile bars colored by Coggan zone. None if no segments.

    Altair is imported here (not at module top) so the pure helpers above stay
    importable in a minimal test environment.
    """
    if not segments:
        return None
    import altair as alt
    import pandas as pd

    rows = []
    t = 0.0
    for seg in segments:
        start = t / 60
        t += seg["duration_s"]
        end = t / 60
        rows.append({
            "start": start, "end": end,
            "pct": round(seg["pct"] * 100),
            "zone": ZONE_NAMES[seg["zone"]],
        })
    df = pd.DataFrame(rows)
    domain = list(ZONE_NAMES.values())
    rng = [ZONE_COLORS[z] for z in ZONE_NAMES]

    x_axis = None if mini else alt.Axis(title="min")
    y_axis = None if mini else alt.Axis(title="% FTP")
    legend = None if mini else alt.Legend(title="Zona")

    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("start:Q", axis=x_axis),
            x2="end:Q",
            y=alt.Y("pct:Q", axis=y_axis),
            color=alt.Color(
                "zone:N",
                scale=alt.Scale(domain=domain, range=rng),
                legend=legend,
            ),
        )
        .properties(height=70 if mini else 240)
    )
