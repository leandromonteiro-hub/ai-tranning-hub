"""Pure helpers + HTML/SVG rendering for the weekly training calendar.

Kept separate from app.py so the data-shaping logic (flattening a structured
workout into colored zone segments, classifying Coggan zones, formatting the
interval list, week date math, adherence) and the visual layer (self-contained
HTML/CSS/SVG strings rendered in a Streamlit component) are pure and
unit-testable without importing streamlit.
"""
from __future__ import annotations

import html as _html
from datetime import date, timedelta

# Coggan 7-zone model, classified by %FTP (fraction). Fixed categorical palette
# so a zone reads the same color everywhere (mirrors the approved mockup).
ZONE_NAMES = {
    1: "Recuperação", 2: "Endurance", 3: "Tempo", 4: "Limiar",
    5: "VO2máx", 6: "Anaeróbico", 7: "Neuromuscular",
}
ZONE_COLORS = {
    1: "#9aa3b2", 2: "#3b82f6", 3: "#10b981", 4: "#f5b400",
    5: "#ff8a3d", 6: "#ef4444", 7: "#8b5cf6",
}

# WorkoutType enum value -> short pt-BR label shown on the day card.
TYPE_LABEL = {
    "ENDURANCE": "Endurance", "RECOVERY": "Recuperação", "TEMPO": "Tempo",
    "SWEET_SPOT": "Sweet Spot", "THRESHOLD": "Limiar", "VO2MAX": "VO2máx",
    "ANAEROBIC": "Anaeróbico", "SPRINT": "Sprint", "OTHER": "Treino",
}

_WEEKDAYS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
_MONTHS_PT = ["", "jan", "fev", "mar", "abr", "mai", "jun",
              "jul", "ago", "set", "out", "nov", "dez"]

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


def block_label_for_week(blocks: list[dict], week: list[date]) -> str:
    """Label ("Bloco BUILD") of the periodization block overlapping `week`, ''."""
    if not blocks or not week:
        return ""
    wk_start, wk_end = week[0], week[-1]
    for b in blocks:
        try:
            bs = date.fromisoformat(b["start_date"])
            be = date.fromisoformat(b["end_date"])
        except (KeyError, TypeError, ValueError):
            continue
        if bs <= wk_end and be >= wk_start:  # block overlaps the displayed week
            bt = b.get("block_type") or ""
            return f"Bloco {bt}" if bt else ""
    return ""


# ── Visual layer: self-contained HTML/CSS/SVG (rendered in a Streamlit
#    component iframe). All functions below are pure string builders. ──────────

_MAX_PCT = 1.5  # bar height saturates at 150% FTP


def dominant_zone(segments: list[dict]) -> int:
    """The hardest zone in the workout (drives the day card's accent dot)."""
    return max((s["zone"] for s in segments), default=2)


def workout_svg(segments: list[dict], *, height: int = 46) -> str:
    """Inline SVG of zone-colored bars (0→%FTP) for one workout. '' if empty."""
    if not segments:
        return ""
    total = sum(s["duration_s"] for s in segments) or 1
    w, pad = 100.0, 1.5
    inner = w - 2 * pad
    x = pad
    rects = []
    for s in segments:
        bw = (s["duration_s"] / total) * inner
        bh = max(3.0, min(1.0, s["pct"] / _MAX_PCT) * (height - 5))
        rects.append(
            f'<rect x="{x:.2f}" y="{height - bh:.2f}" width="{max(0.6, bw - 0.6):.2f}" '
            f'height="{bh:.2f}" rx="1.2" fill="{ZONE_COLORS[s["zone"]]}"/>'
        )
        x += bw
    yftp = height - min(1.0, 1.0 / _MAX_PCT) * (height - 5)
    return (
        f'<svg class="profile" viewBox="0 0 {w:.0f} {height}" preserveAspectRatio="none">'
        f'<line x1="0" y1="{yftp:.1f}" x2="{w:.0f}" y2="{yftp:.1f}" stroke="#cfd6e0" '
        f'stroke-width="0.5" stroke-dasharray="2 2"/>{"".join(rects)}</svg>'
    )


def _adherence_cls(plan_tss: float | None, actual_tss: float | None) -> tuple[str, str]:
    """(css_class, pill_text) for the actual-vs-planned badge. ('','') if n/a."""
    if not plan_tss or actual_tss is None:
        return ("", "")
    ratio = actual_tss / plan_tss
    if ratio >= 0.9:
        return ("good", f"✓ {round(actual_tss)}")
    if ratio >= 0.5:
        return ("warn", f"~ {round(actual_tss)}")
    return ("bad", f"✗ {round(actual_tss)}")


def _day_cell_html(
    d: date, w: dict | None, acts: list[dict], today: date, selected: str | None = None
) -> str:
    is_today = d == today
    is_sel = selected is not None and d.isoformat() == selected
    klass = (" today" if is_today else "") + (" sel" if is_sel else "")
    tag = '<span class="t">HOJE</span>' if is_today else ""
    head = f'<div class="daynum"><span class="d">{d.day}</span>{tag}</div>'
    if not w:
        return (
            f'<div class="cell rest{klass}">{head}'
            f'<div class="rest-label"><span class="ricon">🛌</span>Descanso</div></div>'
        )
    segs = flatten_structure(w.get("structure"))
    zone = dominant_zone(segs)
    name = _html.escape(w.get("name") or "Treino")
    wtype = TYPE_LABEL.get(w.get("workout_type", ""), w.get("workout_type", "Treino"))
    mins = round((w.get("planned_duration_s") or 0) / 60)
    tss = round(w.get("planned_tss") or 0)
    pill = ""
    if d <= today and acts:
        act_tss = sum(c.get("tss") or 0 for c in acts)
        cls, text = _adherence_cls(w.get("planned_tss"), act_tss)
        if cls:
            pill = f'<span class="pill {cls}">{text}</span>'
    return (
        f'<div class="cell{klass}">{head}'
        f'<div class="wk">'
        f'<div class="wk-head"><span class="dot" style="background:{ZONE_COLORS[zone]}"></span>'
        f'<span class="wk-name">{name}</span></div>'
        f'<div class="wk-sub">{wtype} · {mins}min</div>'
        f'{workout_svg(segs)}'
        f'<div class="meta"><span class="tss">{tss} TSS</span>{pill}</div>'
        f'</div></div>'
    )


def _fmt_range(week: list[date]) -> str:
    a, b = week[0], week[6]
    return f"{a.day} {_MONTHS_PT[a.month]} – {b.day} {_MONTHS_PT[b.month]}"


_CALENDAR_CSS = """
*{box-sizing:border-box;margin:0}
body{background:transparent;color:#1f2733;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:100%}
.summary{display:flex;gap:14px;align-items:center;font-size:12.5px;color:#8a93a3;
  font-weight:600;margin-bottom:12px;flex-wrap:wrap}
.summary .rng{font-size:14px;font-weight:700;color:#1f2733}
.summary b{color:#1f2733;font-weight:700}
.blk{font-size:10.5px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;
  color:#3a4658;background:#eef1f5;border:1px solid #e3e7ec;padding:3px 9px;border-radius:20px}
.grid{display:grid;grid-template-columns:repeat(7,1fr);gap:10px}
.dow{font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  color:#8a93a3;padding:0 2px 6px}
.cell{background:#fff;border:1px solid #e3e7ec;border-radius:13px;min-height:176px;
  padding:11px 11px 12px;display:flex;flex-direction:column;gap:8px;
  box-shadow:0 1px 2px rgba(20,30,50,.04)}
.cell.today{border-color:#2f6fed;box-shadow:0 0 0 2px rgba(47,111,237,.16)}
.cell.sel{border-color:#2f6fed;box-shadow:0 0 0 3px rgba(47,111,237,.40)}
.cell.rest{background:#f7f9fb;border-style:dashed}
.daynum{display:flex;align-items:center;justify-content:space-between}
.daynum .d{font-size:14px;font-weight:700}
.daynum .t{font-size:9.5px;font-weight:700;color:#fff;background:#2f6fed;
  padding:2px 7px;border-radius:20px;letter-spacing:.03em}
.wk{display:flex;flex-direction:column;gap:6px;flex:1}
.wk-head{display:flex;align-items:center;gap:6px}
.dot{width:9px;height:9px;border-radius:3px;flex:none}
.wk-name{font-size:12px;font-weight:700;line-height:1.15;letter-spacing:-.01em}
.wk-sub{font-size:10.5px;color:#8a93a3;font-weight:600;margin-top:-2px}
.profile{width:100%;height:44px;display:block}
.meta{display:flex;align-items:center;justify-content:space-between;margin-top:auto}
.tss{font-size:10.5px;color:#8a93a3;font-weight:700}
.pill{font-size:10px;font-weight:800;padding:3px 8px;border-radius:20px}
.pill.good{background:rgba(26,164,106,.12);color:#1aa46a}
.pill.warn{background:rgba(224,160,8,.14);color:#c98a00}
.pill.bad{background:rgba(229,72,77,.12);color:#e5484d}
.rest-label{margin:auto;color:#8a93a3;font-size:11.5px;font-weight:600;display:flex;
  flex-direction:column;align-items:center;gap:5px;opacity:.85}
.ricon{font-size:17px}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:16px;padding-top:13px;
  border-top:1px solid #e3e7ec}
.lg{display:flex;align-items:center;gap:6px;font-size:11px;color:#8a93a3;font-weight:600}
.lg i{width:11px;height:11px;border-radius:3px;display:inline-block}
"""


def calendar_height() -> int:
    """Pixel height for the Streamlit component iframe holding the grid.

    Sized to fit the summary line, weekday row, a full-height day card and the
    zone legend without clipping (scrolling is disabled in the component).
    """
    return 360


def calendar_html(
    week: list[date], by_date: dict, completed: dict, today: date,
    selected: str | None = None, block_label: str = "",
) -> str:
    """Full self-contained HTML document for one week's calendar grid.

    ``selected`` (ISO date) gets a highlighted ring so the grid stays in sync
    with the day chosen for the detail panel. ``block_label`` (e.g. "Bloco
    BUILD") shows the current periodization block in the week summary.
    """
    plan_tss = sum((by_date.get(d.isoformat()) or {}).get("planned_tss") or 0 for d in week)
    act_tss = sum(
        c.get("tss") or 0 for d in week for c in completed.get(d.isoformat(), [])
    )
    blk = f'<span class="blk">{_html.escape(block_label)}</span>' if block_label else ""
    adh = ""
    if act_tss > 0 and plan_tss > 0:
        pct = round(act_tss / plan_tss * 100)
        cls = "good" if pct >= 90 else "warn" if pct >= 50 else "bad"
        adh = f'<span class="pill {cls}">{pct}% adesão</span>'
    dows = "".join(f'<div class="dow">{n}</div>' for n in _WEEKDAYS_PT)
    cells = "".join(
        _day_cell_html(
            d, by_date.get(d.isoformat()), completed.get(d.isoformat(), []), today, selected
        )
        for d in week
    )
    legend = "".join(
        f'<span class="lg"><i style="background:{ZONE_COLORS[z]}"></i>'
        f'Z{z} {ZONE_NAMES[z]}</span>'
        for z in ZONE_NAMES
    )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{_CALENDAR_CSS}</style></head><body><div class='wrap'>"
        f'<div class="summary"><span class="rng">{_fmt_range(week)}</span>{blk}'
        f'<span>Planejado <b>{round(plan_tss)} TSS</b></span>'
        f'<span>Realizado <b>{round(act_tss)} TSS</b></span>{adh}</div>'
        f'<div class="grid">{dows}</div>'
        f'<div class="grid" style="margin-top:6px">{cells}</div>'
        f'<div class="legend">{legend}</div>'
        f"</div></body></html>"
    )


def detail_html(structure: dict | None) -> str:
    """Self-contained HTML for the large workout profile in the detail panel."""
    segs = flatten_structure(structure)
    if not segs:
        return ""
    svg = workout_svg(segs, height=150)
    legend = "".join(
        f'<span class="lg"><i style="background:{ZONE_COLORS[z]}"></i>'
        f'Z{z} {ZONE_NAMES[z]}</span>'
        for z in ZONE_NAMES
    )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><style>{_CALENDAR_CSS}"
        f".big{{background:#fff;border:1px solid #e3e7ec;border-radius:13px;padding:14px}}"
        f".big .profile{{height:150px}}</style></head><body><div class='wrap'>"
        f'<div class="big">{svg}</div>'
        f'<div class="legend" style="margin-top:12px">{legend}</div>'
        f"</div></body></html>"
    )


def detail_height() -> int:
    """Pixel height for the detail-panel component iframe."""
    return 230
