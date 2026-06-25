"""Pure HTML/SVG builders for the training-intelligence dashboard.

Renders what the analysis already computed (form/PMC, FTP timeline, power curve,
intensity distribution, periodization blocks) as self-contained HTML strings for
st.components.v1.html. Pure and unit-testable; no streamlit import.
"""
from __future__ import annotations

import html as _html

# 3-zone polarized intensity palette (easy / moderate / hard).
_SPLIT_COLORS = {"z1": "#3b82f6", "z2": "#f5b400", "z3": "#ef4444"}
_SPLIT_NAMES = {"z1": "Fácil", "z2": "Moderado", "z3": "Forte"}

_CSS = """
*{box-sizing:border-box;margin:0}
body{background:transparent;color:#1f2733;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
.row{display:flex;gap:12px;flex-wrap:wrap}
.card{background:#fff;border:1px solid #e3e7ec;border-radius:13px;padding:13px 15px;
  box-shadow:0 1px 2px rgba(20,30,50,.04);flex:1;min-width:150px}
.card h4{font-size:10.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
  color:#8a93a3;margin-bottom:6px}
.big{font-size:26px;font-weight:800;letter-spacing:-.02em;line-height:1}
.big .u{font-size:13px;font-weight:700;color:#8a93a3;margin-left:3px}
.sub{font-size:11.5px;color:#8a93a3;font-weight:600;margin-top:5px}
.read{font-size:12.5px;font-weight:700;margin-top:5px}
.sec{font-size:13px;font-weight:800;letter-spacing:-.01em;margin:18px 0 9px;color:#1f2733}
.sec:first-child{margin-top:0}
.pill{font-size:10.5px;font-weight:800;padding:3px 9px;border-radius:20px;
  background:#eef1f5;color:#3a4658;border:1px solid #e3e7ec}
.pill.good{background:rgba(26,164,106,.12);color:#1aa46a;border-color:transparent}
.tone-pos{color:#1aa46a}.tone-warn{color:#c98a00}.tone-neg{color:#e5484d}.tone-mut{color:#3a4658}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px}
.lg{display:flex;align-items:center;gap:6px;font-size:11px;color:#8a93a3;font-weight:600}
.lg i{width:11px;height:11px;border-radius:3px;display:inline-block}
.blocks{display:flex;flex-direction:column;gap:6px}
.blk-row{display:flex;gap:10px;align-items:baseline;font-size:11.5px}
.blk-tag{font-size:9.5px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;
  color:#fff;padding:2px 7px;border-radius:5px;flex:none}
.blk-ev{color:#8a93a3;font-weight:600}
.empty{color:#8a93a3;font-size:12.5px;font-weight:600;padding:6px 0}
"""

_BLOCK_COLORS = {
    "base": "#3b82f6", "build": "#ff8a3d", "peak": "#ef4444",
    "taper": "#8b5cf6", "recovery": "#10b981",
}


def form_reading(ctl: float, atl: float, tsb: float) -> str:
    """One-line interpretation of the current form (TSB-driven)."""
    if tsb >= 15:
        return "Descansado — pico de forma"
    if tsb >= 5:
        return "Fresco — pronto para treinar forte"
    if tsb >= -10:
        return "Equilibrado — em forma"
    if tsb >= -30:
        return "Carga produtiva — fatigado"
    return "Muito fatigado — priorize recuperação"


def _tone(tsb: float) -> str:
    if tsb >= 5:
        return "tone-pos"
    if tsb >= -10:
        return "tone-mut"
    if tsb >= -30:
        return "tone-warn"
    return "tone-neg"


def intensity_bar(split: dict | None, *, height: int = 20) -> str:
    """Horizontal stacked bar of the z1/z2/z3 intensity distribution."""
    if not split:
        return ""
    segs = []
    x = 0.0
    for z in ("z1", "z2", "z3"):
        pct = float(split.get(f"{z}_pct") or 0) * 100
        if pct <= 0:
            continue
        segs.append(
            f'<rect x="{x:.2f}" y="0" width="{pct:.2f}" height="{height}" '
            f'fill="{_SPLIT_COLORS[z]}"/>'
        )
        x += pct
    return (
        f'<svg viewBox="0 0 100 {height}" preserveAspectRatio="none" '
        f'style="width:100%;height:{height}px;border-radius:6px;overflow:hidden;display:block">'
        f'{"".join(segs)}</svg>'
    )


def _intensity_legend(split: dict) -> str:
    out = []
    for z in ("z1", "z2", "z3"):
        pct = round(float(split.get(f"{z}_pct") or 0) * 100)
        out.append(
            f'<span class="lg"><i style="background:{_SPLIT_COLORS[z]}"></i>'
            f'{_SPLIT_NAMES[z]} {pct}%</span>'
        )
    return f'<div class="legend">{"".join(out)}</div>'


def power_bars(bests: dict | None) -> str:
    """Vertical bars of best power marks (duration -> watts)."""
    if not bests:
        return ""
    items = list(bests.items())
    mx = max((float(v) for _, v in items), default=1) or 1
    cols = []
    for label, watts in items:
        h = max(4, float(watts) / mx * 90)
        cols.append(
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:4px;flex:1">'
            f'<span style="font-size:11px;font-weight:800">{round(float(watts))}<span class="u" '
            f'style="font-size:9px;color:#8a93a3">W</span></span>'
            f'<div style="width:60%;height:{h:.0f}px;background:#2f6fed;border-radius:4px 4px 0 0"></div>'
            f'<span style="font-size:10px;color:#8a93a3;font-weight:600">{_html.escape(label)}</span>'
            f'</div>'
        )
    return f'<div style="display:flex;gap:8px;align-items:flex-end;height:120px">{"".join(cols)}</div>'


def ftp_bars(ftp_history: list[dict] | None) -> str:
    """Vertical bars of FTP over its validity periods (one bar per period)."""
    if not ftp_history:
        return ""
    # The analysis may persist several FTP rows per period (different methods);
    # collapse to one bar per validity start so the timeline reads cleanly.
    by_period: dict = {}
    for f in ftp_history:
        by_period[f.get("valid_from")] = f
    items = [by_period[k] for k in sorted(by_period, key=lambda x: x or "")]
    mx = max((float(f.get("ftp_watts") or 0) for f in items), default=1) or 1
    cols = []
    for f in items:
        w = float(f.get("ftp_watts") or 0)
        h = max(4, w / mx * 80)
        period = (f.get("valid_from") or "")[:7]
        cols.append(
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:3px;flex:1">'
            f'<span style="font-size:10.5px;font-weight:800">{round(w)}</span>'
            f'<div style="width:55%;height:{h:.0f}px;background:#10b981;border-radius:4px 4px 0 0"></div>'
            f'<span style="font-size:9.5px;color:#8a93a3;font-weight:600">{_html.escape(period)}</span>'
            f'</div>'
        )
    return f'<div style="display:flex;gap:6px;align-items:flex-end;height:110px">{"".join(cols)}</div>'


def _doc(body: str) -> str:
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><style>{_CSS}</style></head>"
        f"<body>{body}</body></html>"
    )


def summary_html(form: dict | None, ftp_current: float | None, split: dict | None) -> str:
    """Compact intelligence strip for the top of the landing page."""
    cards = []
    if form:
        tsb = float(form.get("tsb") or 0)
        cards.append(
            f'<div class="card"><h4>Forma (TSB)</h4>'
            f'<div class="big {_tone(tsb)}">{round(tsb):+d}</div>'
            f'<div class="read {_tone(tsb)}">{form_reading(float(form.get("ctl") or 0), float(form.get("atl") or 0), tsb)}</div></div>'
        )
        cards.append(
            f'<div class="card"><h4>Fitness (CTL)</h4>'
            f'<div class="big">{round(float(form.get("ctl") or 0))}</div>'
            f'<div class="sub">Fadiga (ATL) {round(float(form.get("atl") or 0))}</div></div>'
        )
    if ftp_current:
        cards.append(
            f'<div class="card"><h4>FTP atual</h4>'
            f'<div class="big">{round(ftp_current)}<span class="u">W</span></div></div>'
        )
    if split:
        cards.append(
            f'<div class="card"><h4>Intensidade · {_html.escape(str(split.get("label") or ""))}</h4>'
            f'{intensity_bar(split)}{_intensity_legend(split)}</div>'
        )
    if not cards:
        return ""
    return _doc(f'<div class="row">{"".join(cards)}</div>')


def summary_height() -> int:
    return 140


def _blocks_section(blocks: list[dict]) -> str:
    if not blocks:
        return ""
    recent = blocks[-6:][::-1]  # most recent first
    rows = []
    for b in recent:
        bt = (b.get("block_type") or "").lower()
        color = _BLOCK_COLORS.get(bt, "#8a93a3")
        rows.append(
            f'<div class="blk-row"><span class="blk-tag" style="background:{color}">'
            f'{_html.escape((b.get("block_type") or "").upper())}</span>'
            f'<span class="blk-ev">{_html.escape(b.get("evidence") or "")}</span></div>'
        )
    return (
        f'<div class="sec">🧱 Periodização real · {len(blocks)} blocos detectados</div>'
        f'<div class="blocks">{"".join(rows)}</div>'
    )


def dashboard_html(twin_seed: dict | None, ftp_history: list[dict] | None,
                   form: dict | None) -> str:
    """Full intelligence dashboard."""
    twin = twin_seed or {}
    parts: list[str] = []

    # Form state
    if form:
        ctl = round(float(form.get("ctl") or 0))
        atl = round(float(form.get("atl") or 0))
        tsb = round(float(form.get("tsb") or 0))
        parts.append('<div class="sec">📈 Estado de forma</div>')
        parts.append(
            f'<div class="row">'
            f'<div class="card"><h4>Fitness (CTL)</h4><div class="big">{ctl}</div></div>'
            f'<div class="card"><h4>Fadiga (ATL)</h4><div class="big">{atl}</div></div>'
            f'<div class="card"><h4>Forma (TSB)</h4><div class="big {_tone(tsb)}">{tsb:+d}</div>'
            f'<div class="read {_tone(tsb)}">{form_reading(ctl, atl, tsb)}</div></div>'
            f'</div>'
        )

    # FTP timeline
    if ftp_history:
        cur = round(float(ftp_history[-1].get("ftp_watts") or 0))
        parts.append(f'<div class="sec">⚡ FTP · atual {cur} W</div>')
        parts.append(f'<div class="card">{ftp_bars(ftp_history)}</div>')

    # Power curve
    bests = twin.get("power_curve_bests") or twin.get("best_marks")
    if bests:
        parts.append('<div class="sec">🚴 Curva de potência (melhores marcas)</div>')
        parts.append(f'<div class="card">{power_bars(bests)}</div>')

    # Intensity distribution
    split = twin.get("intensity_split")
    if split:
        parts.append(f'<div class="sec">🎯 Distribuição de intensidade · {_html.escape(str(split.get("label") or ""))}</div>')
        parts.append(f'<div class="card">{intensity_bar(split, height=26)}{_intensity_legend(split)}</div>')

    # Blocks
    parts.append(_blocks_section(twin.get("block_summary") or []))

    # Data richness
    dr = twin.get("data_richness") or {}
    if dr.get("score") is not None:
        score = float(dr["score"])
        label = "alta" if score >= 0.75 else "média" if score >= 0.4 else "baixa"
        parts.append(
            f'<div class="sec">📊 Riqueza dos dados</div>'
            f'<span class="pill good">{label} · score {score:.2f}</span>'
        )

    if not any(parts):
        return _doc('<div class="empty">Perfil de inteligência ainda não gerado. '
                    'Rode a análise do atleta para computar o gêmeo digital.</div>')
    return _doc("".join(parts))


def dashboard_height(twin_seed: dict | None) -> int:
    """Rough iframe height for the dashboard based on how many sections render."""
    base = 130  # form
    twin = twin_seed or {}
    if twin.get("power_curve_bests") or twin.get("best_marks"):
        base += 190
    base += 190  # ftp
    if twin.get("intensity_split"):
        base += 120
    blocks = twin.get("block_summary") or []
    if blocks:
        base += 60 + min(len(blocks), 6) * 26
    if (twin.get("data_richness") or {}).get("score") is not None:
        base += 70
    return base
