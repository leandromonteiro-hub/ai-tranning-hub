# Plan Calendar View (calendário de treinos estilo TrainingPeaks) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir a tabela plana de treinos diários por um calendário semanal (7 colunas Seg–Dom) onde cada dia mostra o perfil do treino em barras coloridas por zona (estilo TrainingPeaks), com overlay planejado×realizado e painel de detalhe com download .zwo/.fit.

**Architecture:** Backend expõe `structure` na listagem de treinos planejados (mudança de schema, sem rota nova). Um novo módulo `frontend/calendar_view.py` concentra funções puras (achatamento da estrutura em segmentos por zona, classificação Coggan, formatação de intervalos, adesão, datas da semana) testáveis sem Streamlit, mais um render `profile_chart` em Altair (import preguiçoso). O `plan_tab` em `frontend/app.py` passa a renderizar a grade semanal + painel de detalhe; o realizado vem de `GET /workouts?start&end` (já existe).

**Tech Stack:** FastAPI/SQLAlchemy/Pydantic/pytest (backend); Streamlit + Altair + pandas (frontend). Spec: `docs/superpowers/specs/2026-06-25-plan-calendar-view-design.md`.

## Global Constraints

- **Abordagem A** (Streamlit nativo + Altair). Sem HTML/SVG custom, sem dependências novas (altair/pandas já estão no `frontend/Dockerfile`).
- **Sem rota nova de backend.** Planejados: `GET /plans/{plan_id}/workouts` (alargar schema). Realizados: `GET /workouts?start=&end=` (existente; `WorkoutCompletedRead` tem `workout_date`, `workout_type`, `duration_s`, `tss`, `intensity_factor`).
- **Funções puras em `calendar_view.py` não importam streamlit nem altair no topo do módulo** — altair é importado dentro de `profile_chart`. Isso mantém os testes rodáveis em container slim.
- **Zonas Coggan por fração de FTP:** Z1 <0.56, Z2 <0.76, Z3 <0.91, Z4 <1.06, Z5 <1.21, Z6 <1.51, Z7 ≥1.51. Segmento `open`/sem target → 0.45 (zona 1).
- **Escopo v1:** só treinos planejados com selo de adesão do realizado (não a curva real por-segundo). Remover a tabela plana de dias; manter as barras de TSS por semana + resumo de blocos.
- Código em inglês; textos de UI em português.
- **Test cmds:**
  - Backend: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -v"`
  - Frontend (funções + chart): `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest altair pandas && cd /f && python -m pytest test_calendar_view.py -v"`
  - Sintaxe: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); ast.parse(open('/f/calendar_view.py',encoding='utf-8').read()); print('ok')"`

---

### Task 1: Backend — expor `structure` e `name` em `PlannedWorkoutRead`

**Files:**
- Modify: `backend/app/schemas/planning.py` (classe `PlannedWorkoutRead`)
- Modify (test): `backend/app/tests/test_api/test_plan_expand.py` (`test_list_plan_workouts`)

**Interfaces:**
- Produces: `PlannedWorkoutRead` agora inclui `name: str` e `structure: dict | None`. Consumido pelo frontend (`flatten_structure`, label do dia).

- [ ] **Step 1: Atualizar o teste para exigir `structure`+`name`** — em `backend/app/tests/test_api/test_plan_expand.py`, dentro de `test_list_plan_workouts`, após a linha `assert all(r["workout_type"] and r["id"] for r in rows)`, acrescentar:
```python
    assert all(r.get("structure") for r in rows)
    assert all(r.get("name") for r in rows)
```

- [ ] **Step 2: Rodar → FALHA** (schema não retorna `structure`/`name`).
Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_plan_expand.py::test_list_plan_workouts -v"`
Expected: FAIL no `assert all(r.get("structure") ...)`.

- [ ] **Step 3: Alargar o schema** — em `backend/app/schemas/planning.py`, na classe `PlannedWorkoutRead`, adicionar `name` e `structure` (manter os campos existentes). A classe inteira fica:
```python
class PlannedWorkoutRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    planned_date: date
    name: str
    workout_type: WorkoutType
    planned_duration_s: int | None = None
    planned_tss: float | None = None
    description: str | None = None
    structure: dict | None = None
```

- [ ] **Step 4: Rodar → PASSA.**
Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest app/tests/test_api/test_plan_expand.py -v"`
Expected: 5 passed.

- [ ] **Step 5: Commit**
```bash
git add backend/app/schemas/planning.py backend/app/tests/test_api/test_plan_expand.py
git commit -m "feat(plan): expose structure+name in PlannedWorkoutRead (calendar profile)"
```

---

### Task 2: Frontend — `calendar_view.py` funções puras + testes

**Files:**
- Create: `frontend/calendar_view.py` (apenas as funções puras nesta task; `profile_chart` vem na Task 3)
- Create (test): `frontend/test_calendar_view.py`

**Interfaces:**
- Produces:
  - `ZONE_NAMES: dict[int,str]`, `ZONE_COLORS: dict[int,str]`
  - `zone_of(pct: float) -> int`
  - `flatten_structure(structure: dict | None) -> list[dict]` — cada segmento `{intensity, duration_s, pct, zone}`
  - `interval_lines(structure: dict | None) -> list[str]`
  - `adherence(plan_tss: float | None, actual_tss: float | None) -> tuple[str, str]`
  - `week_dates(anchor: date) -> list[date]` (Seg..Dom da semana de `anchor`)

- [ ] **Step 1: Escrever os testes que falham** — `frontend/test_calendar_view.py`:
```python
from datetime import date

from calendar_view import (
    adherence,
    flatten_structure,
    interval_lines,
    week_dates,
    zone_of,
)

_STRUCT = {
    "name": "VO2 4x4",
    "elements": [
        {"intensity": "warmup", "duration_s": 600,
         "target": {"type": "power_pct_ftp", "low": 0.55, "high": 0.65}},
        {"count": 3, "steps": [
            {"intensity": "active", "duration_s": 300,
             "target": {"type": "power_pct_ftp", "low": 1.1, "high": 1.1}},
            {"intensity": "rest", "duration_s": 180,
             "target": {"type": "power_pct_ftp", "low": 0.5, "high": 0.5}},
        ]},
        {"intensity": "cooldown", "duration_s": 300,
         "target": {"type": "power_pct_ftp", "low": 0.55, "high": 0.55}},
    ],
}


def test_zone_of_boundaries():
    assert zone_of(0.50) == 1
    assert zone_of(0.60) == 2
    assert zone_of(0.80) == 3
    assert zone_of(1.00) == 4
    assert zone_of(1.10) == 5
    assert zone_of(1.30) == 6
    assert zone_of(1.60) == 7


def test_flatten_expands_repeats():
    segs = flatten_structure(_STRUCT)
    # warmup + 3*(active+rest) + cooldown = 1 + 6 + 1 = 8
    assert len(segs) == 8
    assert sum(s["duration_s"] for s in segs) == 600 + 3 * (300 + 180) + 300
    assert segs[1]["zone"] == 5  # the active VO2 step


def test_flatten_empty():
    assert flatten_structure(None) == []
    assert flatten_structure({}) == []


def test_interval_lines_formats_repeat_and_endpoints():
    lines = interval_lines(_STRUCT)
    assert lines[0].startswith("Aquecimento 10min @ 55-65%")
    assert any(l.startswith("3× 5min @ 110% / 3min @ 50%") for l in lines)
    assert lines[-1].startswith("Volta à calma 5min @ 55%")


def test_adherence_thresholds():
    assert adherence(100, 95)[0] == "✅"
    assert adherence(100, 70)[0] == "🟡"
    assert adherence(100, 30)[0] == "🔴"
    assert adherence(None, 50) == ("", "")
    assert adherence(100, None) == ("", "")


def test_week_dates_monday_to_sunday():
    wd = week_dates(date(2026, 6, 25))  # quinta
    assert wd[0] == date(2026, 6, 22)   # segunda
    assert wd[6] == date(2026, 6, 28)   # domingo
    assert len(wd) == 7
```

- [ ] **Step 2: Rodar → FALHA** (módulo inexistente).
Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest altair pandas && cd /f && python -m pytest test_calendar_view.py -v"`
Expected: erro de import `No module named 'calendar_view'`.

- [ ] **Step 3: Implementar as funções puras** — `frontend/calendar_view.py`:
```python
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
    ratio = actual_tss / plan_tss if plan_tss else 0
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
```

- [ ] **Step 4: Rodar → PASSA.**
Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest altair pandas && cd /f && python -m pytest test_calendar_view.py -v"`
Expected: 6 passed.

- [ ] **Step 5: Commit**
```bash
git add frontend/calendar_view.py frontend/test_calendar_view.py
git commit -m "feat(frontend): calendar_view pure helpers (zones, flatten, intervals, adherence)"
```

---

### Task 3: Frontend — `profile_chart` (Altair) + smoke test

**Files:**
- Modify: `frontend/calendar_view.py` (adicionar `profile_chart`)
- Modify (test): `frontend/test_calendar_view.py`

**Interfaces:**
- Consumes: segmentos de `flatten_structure`, `ZONE_NAMES`/`ZONE_COLORS`.
- Produces: `profile_chart(segments: list[dict], *, mini: bool = True)` → objeto `alt.Chart` (ou `None` se `segments == []`). Barras (`mark_bar`) de 0 até %FTP por intervalo, coloridas por zona; `mini=True` sem eixos/legenda (célula), `mini=False` com eixos+legenda (detalhe).

- [ ] **Step 1: Escrever o smoke test** — acrescentar ao final de `frontend/test_calendar_view.py`:
```python
from calendar_view import profile_chart


def test_profile_chart_none_when_empty():
    assert profile_chart([]) is None


def test_profile_chart_builds_for_segments():
    segs = flatten_structure(_STRUCT)
    ch = profile_chart(segs, mini=False)
    assert ch is not None
    spec = ch.to_dict()  # raises if the Vega-Lite spec is malformed
    assert isinstance(spec, dict)
    mini = profile_chart(segs, mini=True)
    assert mini.to_dict()["height"] == 70
```

- [ ] **Step 2: Rodar → FALHA** (`profile_chart` não existe / ImportError).
Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest altair pandas && cd /f && python -m pytest test_calendar_view.py -v"`
Expected: ImportError de `profile_chart` (ou falha de coleta).

- [ ] **Step 3: Implementar `profile_chart`** — acrescentar ao final de `frontend/calendar_view.py`:
```python
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
```

- [ ] **Step 4: Rodar → PASSA.**
Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest altair pandas && cd /f && python -m pytest test_calendar_view.py -v"`
Expected: 8 passed.

- [ ] **Step 5: Commit**
```bash
git add frontend/calendar_view.py frontend/test_calendar_view.py
git commit -m "feat(frontend): profile_chart — zone-colored stepped workout profile (Altair)"
```

---

### Task 4: Frontend — calendário semanal + painel de detalhe no `plan_tab`

**Files:**
- Modify: `frontend/app.py` (import de `calendar_view`; substituir o bloco "Treinos diários até a prova"; adicionar `_render_calendar` e `_render_day_detail`)

**Interfaces:**
- Consumes: `calendar_view` (`flatten_structure`, `profile_chart`, `interval_lines`, `adherence`, `week_dates`); `GET /plans/{id}/workouts` (com `structure`); `GET /workouts?start&end`; `GET /plans/workouts/{id}/export.{ext}`.
- Produces: UI (sem interface programática consumida por outras tasks).

- [ ] **Step 1: Adicionar o import do módulo** — em `frontend/app.py`, logo após `import streamlit as st` (linha ~15), acrescentar:
```python
import calendar_view as cv
```

- [ ] **Step 2: Adicionar a constante de dias da semana** — em `frontend/app.py`, imediatamente antes de `def plan_tab(token: str) -> None:` (linha ~244), inserir:
```python
_WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
```

- [ ] **Step 3: Substituir o bloco da tabela plana pelo calendário** — em `frontend/app.py`, substituir TODO o trecho atual que começa em `    st.divider()` / `    st.markdown("#### Treinos diários até a prova")` e termina na chamada `key=f"dl_{ext}_{chosen['id']}")` (o bloco que monta `wl`, a `st.dataframe` dos dias, o `selectbox` e os `download_button`) por:
```python
    st.divider()
    st.markdown("#### 📅 Calendário de treinos")
    if st.button("Gerar treinos diários até a prova"):
        r = api("POST", f"/plans/{plan['id']}/expand", token=token)
        if r.status_code == 201:
            d = r.json()
            st.success(f"{d['days']} treinos gerados ({d['start']} → {d['end']}, TSS total {d['tss_total']}).")
            st.rerun()
        else:
            st.error(r.text)

    wl = api("GET", f"/plans/{plan['id']}/workouts", token=token)
    daily = wl.json() if wl.status_code == 200 else []
    if not daily:
        st.info("Nenhum treino diário ainda. Clique acima para gerar.")
        return
    _render_calendar(token, daily)
```

- [ ] **Step 4: Adicionar `_render_calendar` e `_render_day_detail`** — em `frontend/app.py`, imediatamente após o fim de `plan_tab` (antes de `def checkin_tab`), inserir:
```python
def _render_calendar(token: str, daily: list[dict]) -> None:
    by_date = {w["planned_date"]: w for w in daily}
    dates = sorted(by_date)
    plan_start = date.fromisoformat(dates[0])
    plan_end = date.fromisoformat(dates[-1])

    # Completed workouts across the plan window (actual overlay).
    cw = api("GET", "/workouts", token=token, params={"start": dates[0], "end": dates[-1]})
    completed: dict[str, list[dict]] = {}
    if cw.status_code == 200:
        for c in cw.json():
            completed.setdefault(c["workout_date"], []).append(c)

    if "plan_week_offset" not in st.session_state:
        st.session_state["plan_week_offset"] = 0
    today = date.today()
    anchor = today + timedelta(weeks=st.session_state["plan_week_offset"])
    if anchor < plan_start:
        anchor = plan_start
    if anchor > plan_end:
        anchor = plan_end
    week = cv.week_dates(anchor)

    nav1, nav2, nav3, nav4 = st.columns([1, 1, 1, 3])
    if nav1.button("◀ Semana"):
        st.session_state["plan_week_offset"] -= 1
        st.rerun()
    if nav2.button("Hoje"):
        st.session_state["plan_week_offset"] = 0
        st.rerun()
    if nav3.button("Semana ▶"):
        st.session_state["plan_week_offset"] += 1
        st.rerun()
    week_plan = sum((by_date.get(d.isoformat()) or {}).get("planned_tss") or 0 for d in week)
    week_act = sum(c.get("tss") or 0 for d in week for c in completed.get(d.isoformat(), []))
    nav4.markdown(
        f"**{week[0].strftime('%d/%m')} – {week[6].strftime('%d/%m')}** · "
        f"plan {round(week_plan)} TSS · feito {round(week_act)} TSS"
    )

    cols = st.columns(7)
    for i, d in enumerate(week):
        iso = d.isoformat()
        with cols[i]:
            st.markdown(f"**{'🔵 ' if d == today else ''}{_WEEKDAYS[i]} {d.day}**")
            w = by_date.get(iso)
            if w:
                ch = cv.profile_chart(cv.flatten_structure(w.get("structure")), mini=True)
                if ch is not None:
                    st.altair_chart(ch, use_container_width=True)
                st.caption(f"{w['workout_type']} · {round(w.get('planned_tss') or 0)} TSS")
                acts = completed.get(iso, [])
                if d <= today and acts:
                    act_tss = sum(c.get("tss") or 0 for c in acts)
                    emoji, _ = cv.adherence(w.get("planned_tss"), act_tss)
                    dur = round(sum(c.get("duration_s") or 0 for c in acts) / 60)
                    st.caption(f"{emoji} {round(act_tss)} TSS · {dur}min")
                if st.button("ver", key=f"day_{iso}"):
                    st.session_state["plan_sel_date"] = iso
            else:
                st.caption("descanso")

    sel = st.session_state.get("plan_sel_date")
    if sel and sel in by_date:
        _render_day_detail(token, by_date[sel], completed.get(sel, []), sel)


def _render_day_detail(token: str, w: dict, acts: list[dict], iso: str) -> None:
    st.divider()
    d = date.fromisoformat(iso)
    st.markdown(
        f"### {d.strftime('%d/%m')} · {w['workout_type']} · "
        f"{round((w.get('planned_duration_s') or 0) / 60)}min · {round(w.get('planned_tss') or 0)} TSS"
    )
    ch = cv.profile_chart(cv.flatten_structure(w.get("structure")), mini=False)
    if ch is not None:
        st.altair_chart(ch, use_container_width=True)
    for line in cv.interval_lines(w.get("structure")):
        st.write(f"- {line}")
    if acts:
        act_tss = sum(c.get("tss") or 0 for c in acts)
        dur = round(sum(c.get("duration_s") or 0 for c in acts) / 60)
        ifs = [c.get("intensity_factor") for c in acts if c.get("intensity_factor")]
        emoji, _ = cv.adherence(w.get("planned_tss"), act_tss)
        if_txt = f" · IF {max(ifs):.2f}" if ifs else ""
        st.info(f"{emoji} Realizado: {round(act_tss)} TSS · {dur}min{if_txt}")
    c1, c2 = st.columns(2)
    for col, ext in ((c1, "zwo"), (c2, "fit")):
        resp = api("GET", f"/plans/workouts/{w['id']}/export.{ext}", token=token)
        if resp.status_code == 200:
            col.download_button(
                f"⬇️ .{ext}", data=resp.content,
                file_name=f"treino_{iso}.{ext}",
                mime="application/octet-stream", key=f"dl_{ext}_{w['id']}",
            )
```

- [ ] **Step 5: Checar sintaxe dos dois arquivos.**
Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); ast.parse(open('/f/calendar_view.py',encoding='utf-8').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 6: Verificação ao vivo.**
Run: `docker compose up -d --build api frontend`
Manual: abrir http://localhost:8501, logar (`leandro@athletehub.example.com` / `leandro12345`), aba 📅 Plano → gerar treinos (se ainda não houver) → ver a grade semanal com perfis coloridos, navegar ◀/Hoje/▶, clicar "ver" em um dia → conferir o painel de detalhe (perfil grande + lista de intervalos + selo de realizado se houver) e baixar .zwo/.fit.

- [ ] **Step 7: Commit**
```bash
git add frontend/app.py
git commit -m "feat(frontend): weekly training calendar with zone profiles + plan/actual overlay"
```

---

## Self-Review (autor do plano)

- **Cobertura do spec:**
  - Vista semanal 7 colunas + navegação → Task 4 (`week_dates`, `_render_calendar`, botões ◀/Hoje/▶).
  - Perfil em degraus colorido por zona → Tasks 2 (`flatten_structure`/`zone_of`) + 3 (`profile_chart`).
  - Painel de detalhe (perfil grande, intervalos, download) → Task 4 (`_render_day_detail`), `interval_lines` (Task 2), export reusa rotas existentes.
  - Overlay planejado×realizado (selo de adesão) → `adherence` (Task 2) + `GET /workouts` em `_render_calendar` (Task 4).
  - Expor `structure` p/ desenhar o perfil → Task 1.
  - Remover tabela plana, manter barras de TSS por semana + blocos → Task 4 Step 3 substitui só o bloco diário; o trecho das semanas (linhas ~278-292) permanece intocado.
  - Zonas Coggan, cores fixas, segmento `open`→0.45 → Task 2 (`zone_of`, `_target_mid`, `ZONE_COLORS`).
  - Degrada bem sem estrutura → `flatten_structure([])`/`profile_chart(None)` retornam vazio/None; célula mostra só tipo/TSS.
- **Placeholders:** nenhum "TBD"; todo código completo.
- **Consistência de tipos:** `flatten_structure` produz segmentos `{intensity,duration_s,pct,zone}` consumidos por `profile_chart` (Task 3) e contados nos testes (Task 2); `adherence`/`interval_lines`/`week_dates` usados em `_render_calendar`/`_render_day_detail` (Task 4) com as mesmas assinaturas; `PlannedWorkoutRead.structure` (Task 1) é o que `w.get("structure")` lê no frontend.
- **Risco conhecido:** `profile_chart` é testado só por smoke (tipo de retorno + altura); a aparência fica para a verificação ao vivo (Task 4 Step 6) — coerente com o frontend não ter harness de UI. `mini.to_dict()["height"]` assume que Altair serializa `height` no topo do spec (verdadeiro para chart de camada única com `.properties(height=...)`).
```
