"""Athlete AI Training Hub — Streamlit validation UI.

Minimal, purpose-built for the 2-athlete validation: log in, import history,
set a target race, generate a periodized plan, request a phase-aware
recommendation, and give feedback. Chosen over Next.js for the MVP because it
ships a working feedback loop in one Python codebase with near-zero overhead.
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta

import httpx
import pandas as pd
import streamlit as st
import calendar_view as cv
import intelligence_view as iv
import streamlit.components.v1 as components
from job_poll import poll_decision

API = os.environ.get("STREAMLIT_API_BASE_URL", "http://localhost:8000/api/v1")

st.set_page_config(page_title="Athlete AI Training Hub", layout="wide")


def api(method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # Real LLM recommendations (claude-opus) can take ~30-35s; keep the client
    # timeout well above that so the UI doesn't fail a request the API completes.
    timeout = kwargs.pop("timeout", 120)
    return httpx.request(method, f"{API}{path}", headers=headers, timeout=timeout, **kwargs)


def login_view() -> None:
    st.title("🚴 Athlete AI Training Hub")
    st.caption("Fase de validação — entre com sua conta de atleta")
    with st.form("login"):
        email = st.text_input("Email", value="athlete1@athletehub.example.com")
        password = st.text_input("Senha", type="password", value="athlete1_pwd")
        if st.form_submit_button("Entrar"):
            resp = api("POST", "/auth/login", data={"username": email, "password": password})
            if resp.status_code == 200:
                st.session_state["token"] = resp.json()["access_token"]
                st.rerun()
            else:
                st.error(f"Falha no login: {resp.text}")


def _sample_workouts_sidebar(token: str) -> None:
    with st.sidebar.expander("🧪 Treinos de teste"):
        st.caption(
            "Baixe um treino estruturado de exemplo. **.zwo** para importar no "
            "TrainingPeaks (Workout Library); **.fit** para o device via USB."
        )
        ftp = st.number_input("FTP (W)", min_value=80, max_value=600, value=250, step=5)
        samples = [
            ("Sweet Spot 3×12", "sweet_spot"),
            ("VO2max 5×4", "vo2max"),
            ("Endurance Z2", "endurance"),
            ("Recuperação Z1", "recovery"),
        ]
        for label, template in samples:
            st.markdown(f"**{label}**")
            c1, c2 = st.columns(2)
            for col, ext in ((c1, "zwo"), (c2, "fit")):
                resp = api("GET", f"/recommendations/sample.{ext}", token=token,
                           params={"template": template, "ftp": ftp})
                if resp.status_code == 200:
                    col.download_button(
                        f"⬇️ .{ext}",
                        data=resp.content,
                        file_name=f"{template}_ftp{int(ftp)}.{ext}",
                        mime="application/octet-stream",
                        key=f"sample_{template}_{ext}",
                    )


def _fetch_intelligence(token: str) -> dict:
    r = api("GET", "/athletes/me/intelligence", token=token)
    return r.json() if r.status_code == 200 else {}


def _intelligence_summary(token: str) -> None:
    """Compact intelligence strip rendered at the top of the landing page."""
    d = _fetch_intelligence(token)
    ftp_hist = d.get("ftp_history") or []
    ftp_cur = ftp_hist[-1]["ftp_watts"] if ftp_hist else None
    split = (d.get("twin_seed") or {}).get("intensity_split")
    html = iv.summary_html(d.get("form"), ftp_cur, split)
    if html:
        components.html(html, height=iv.summary_height(), scrolling=False)


def load_tab(token: str) -> None:
    st.subheader("📊 Inteligência de treino")
    d = _fetch_intelligence(token)
    twin = d.get("twin_seed")
    components.html(
        iv.dashboard_html(twin, d.get("ftp_history") or [], d.get("form")),
        height=iv.dashboard_height(twin), scrolling=True,
    )

    st.divider()
    st.markdown("##### Tendência · CTL (fitness) · ATL (fadiga) · TSB (forma)")
    if st.button("Recalcular métricas"):
        api("POST", "/metrics/load/recompute", token=token)
        st.rerun()
    resp = api("GET", "/metrics/load", token=token)
    rows = resp.json() if resp.status_code == 200 else []
    if rows:
        df = pd.DataFrame(rows)
        df["metric_date"] = pd.to_datetime(df["metric_date"])
        st.line_chart(df.set_index("metric_date")[["ctl", "atl", "tsb"]])
    else:
        st.info("Sem dados de carga ainda. Importe treinos na aba Importar.")


def import_tab(token: str) -> None:
    st.subheader("Importar arquivos (CSV TrainingPeaks, FIT, TCX, GPX)")
    files = st.file_uploader(
        "Selecione arquivos", accept_multiple_files=True,
        type=["csv", "fit", "tcx", "gpx"],
    )
    if files and st.button("Enviar"):
        multipart = [("files", (f.name, f.getvalue())) for f in files]
        resp = api("POST", "/imports/upload", token=token, files=multipart)
        if resp.status_code != 200:
            st.error(resp.text)
            return
        body = resp.json()
        st.success("Importação concluída")
        st.dataframe(pd.DataFrame(body.get("files", [])))

        task_id = body.get("profile_task_id")
        if task_id:
            _await_profile_regen(token, task_id)


def _await_profile_regen(token: str, task_id: str, max_attempts: int = 30) -> None:
    """Poll the async profile-regeneration job and report when the profile is fresh."""
    with st.spinner("🔄 Atualizando seu perfil…"):
        for attempt in range(1, max_attempts + 1):
            r = api("GET", f"/jobs/{task_id}", token=token)
            state = r.json().get("state", "PENDING") if r.status_code == 200 else "PENDING"
            decision = poll_decision(state, attempt, max_attempts)
            if decision == "done":
                # toast sobrevive ao rerun; rerun faz o painel de inteligência
                # recarregar o perfil recém-regerado sem esperar outra interação.
                st.toast("Perfil atualizado.", icon="✅")
                st.rerun()
            if decision == "failed":
                st.warning("O perfil será atualizado em instantes.")
                return
            if decision == "giveup":
                st.info("O perfil está sendo atualizado em segundo plano.")
                return
            time.sleep(1)


def recommendations_tab(token: str, anamnese_ok: bool = True) -> None:
    st.subheader("Recomendação de treino")
    if not anamnese_ok:
        st.info("Complete sua anamnese (aba 🩺 Anamnese) para gerar recomendações.")
        return
    _plan = _latest_plan(token)
    _phase = _current_phase(_plan) if _plan else None
    if _phase:
        st.info(f"Hoje: fase **{_phase['block_type']}** · semana {_phase['week_index']}/{_plan['total_weeks']}")
    else:
        st.caption("Sem plano ativo cobrindo hoje — a recomendação usará o bloco padrão (BASE).")
    question = st.text_input("Pergunta (opcional)", "Qual treino devo fazer hoje?")
    if st.button("Gerar recomendação"):
        resp = api("POST", "/recommendations", token=token, json={"question": question})
        if resp.status_code == 201:
            st.session_state["last_rec"] = resp.json()
        else:
            st.error(resp.text)

    rec = st.session_state.get("last_rec")
    if rec:
        risk = rec["risk_level"]
        color = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🔴"}.get(risk, "⚪")
        st.markdown(f"### {color} Risco: {risk}  ·  Confiança: {rec.get('confidence')}")
        st.write(rec["summary"])

        sig = (rec.get("payload") or {}).get("signals") or {}
        if sig:
            with st.expander("🔍 Baseado em (sinais que embasaram esta recomendação)", expanded=True):
                form = sig.get("form") or {}
                ctl, atl, tsb = form.get("ctl"), form.get("atl"), form.get("tsb")
                c1, c2, c3 = st.columns(3)
                c1.metric("Fitness (CTL)", round(ctl) if ctl is not None else "—")
                c2.metric("Fadiga (ATL)", round(atl) if atl is not None else "—")
                c3.metric("Forma (TSB)", round(tsb) if tsb is not None else "—")
                if tsb is not None:
                    st.caption(f"Estado: {iv.form_reading(ctl or 0, atl or 0, tsb)}")
                cc = st.columns(2)
                cc[0].markdown(f"**Bloco atual:** {sig.get('block') or '—'}")
                cc[1].markdown(f"**FTP usado:** {sig.get('ftp_watts') or '—'} W")
                meth = sig.get("methodology")
                if meth and meth != "n/d":
                    st.markdown(f"**Metodologia (perfil reverso real):** {meth}")
                fb_line = iv.feedback_line(sig.get("feedback"))
                if fb_line:
                    st.caption(fb_line)

        with st.expander("Justificativa, evidências e ajustes"):
            st.write("**Objetivo fisiológico:**", rec.get("physiological_objective"))
            st.write("**Relação com o bloco:**", rec.get("block_relation"))
            st.write("**Racional:**", rec.get("rationale"))
            st.write("**Se mais cansado:**", rec.get("adjust_if_tired"))
            st.write("**Se menos tempo:**", rec.get("adjust_if_less_time"))
            st.write("**Evidências (histórico real):**")
            for e in rec.get("evidence", []):
                st.write(f"- {e['description']}")

        payload = rec.get("payload") or {}
        desc = payload.get("workout_description")
        if desc:
            st.markdown("#### 🏋️ Treino estruturado")
            st.code(desc, language=None)

        has_structured = bool(payload.get("structured_workout"))
        if has_structured:
            st.markdown("**Baixar treino:**")
            col_zwo, col_fit = st.columns(2)
            for col, ext, hint in (
                (col_zwo, "zwo", "TrainingPeaks"),
                (col_fit, "fit", "device via USB"),
            ):
                resp = api("GET", f"/recommendations/{rec['id']}/export.{ext}", token=token)
                if resp.status_code == 200:
                    col.download_button(
                        f"⬇️ .{ext} ({hint})",
                        data=resp.content,
                        file_name=f"treino_{rec['id'][:8]}.{ext}",
                        mime="application/octet-stream",
                        key=f"rec_export_{ext}",
                    )

        st.divider()
        st.markdown("#### Seu feedback após executar")
        rating = st.slider("Nota", 1, 5, 4)
        made_sense = st.checkbox("Fez sentido para mim", value=True)
        comment = st.text_area("Comentário")
        if st.button("Enviar feedback"):
            fb = api(
                "POST", f"/feedback/{rec['id']}", token=token,
                json={"rating": rating, "made_sense": made_sense, "comment": comment},
            )
            st.success("Feedback registrado. Obrigado!") if fb.status_code == 201 else st.error(fb.text)


def races_tab(token: str) -> None:
    st.subheader("Provas-alvo")
    with st.form("nova_prova"):
        name = st.text_input("Nome da prova")
        race_date = st.date_input("Data da prova")
        discipline = st.text_input("Disciplina (ex.: XCO, Maratona)", "")
        priority = st.selectbox("Prioridade", ["A", "B", "C"], index=0)
        with st.expander("Mais detalhes (opcional)"):
            location = st.text_input("Local", "")
            distance_km = st.number_input("Distância (km)", min_value=0.0, value=0.0, step=1.0)
            elevation_gain_m = st.number_input("Ganho de elevação (m)", min_value=0.0, value=0.0, step=50.0)
            notes = st.text_area("Notas", "")
        if st.form_submit_button("Cadastrar prova"):
            if not name:
                st.error("Informe o nome da prova.")
            else:
                body = {
                    "name": name,
                    "race_date": race_date.isoformat(),
                    "discipline": discipline or None,
                    "priority": priority,
                    "location": location or None,
                    "distance_km": distance_km or None,
                    "elevation_gain_m": elevation_gain_m or None,
                    "notes": notes or None,
                }
                resp = api("POST", "/races", token=token, json=body)
                if resp.status_code == 201:
                    st.success("Prova cadastrada.")
                    st.rerun()
                else:
                    st.error(resp.text)

    resp = api("GET", "/races", token=token)
    races = resp.json() if resp.status_code == 200 else []
    if races:
        df = pd.DataFrame([
            {"Data": r["race_date"], "Prova": r["name"],
             "Prioridade": r.get("priority"), "Disciplina": r.get("discipline") or "—"}
            for r in races
        ])
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.info("Nenhuma prova cadastrada ainda. Cadastre acima.")


def _fmt_race_label(r: dict) -> str:
    return f"{r['race_date']} — {r['name']} (P{r.get('priority', '?')})"


def _latest_plan(token: str) -> dict | None:
    resp = api("GET", "/plans", token=token)
    plans = resp.json() if resp.status_code == 200 else []
    return max(plans, key=lambda p: p["start_date"]) if plans else None


def _current_phase(plan: dict) -> dict | None:
    """The plan week whose [week_start, week_start+7d) contains today, or None."""
    today = date.today()
    for w in plan.get("weeks", []):
        start = date.fromisoformat(w["week_start"])
        if start <= today < start + timedelta(days=7):
            return w
    return None




def _plan_generation_controls(token: str) -> None:
    """Race selection + 'generate plan' button (reused on the empty state and
    inside the management expander)."""
    resp = api("GET", "/races", token=token)
    races = resp.json() if resp.status_code == 200 else []
    if not races:
        st.info("Cadastre uma prova na aba 🏁 Provas para gerar um plano.")
        return
    labels = {_fmt_race_label(r): r for r in races}
    choice = st.selectbox("Prova-alvo", list(labels.keys()))
    priority = st.selectbox("Prioridade do plano", ["A", "B", "C"], index=0, key="plan_prio")
    if st.button("Gerar plano"):
        race = labels[choice]
        body = {
            "name": f"Plano — {race['name']}",
            "race_date": race["race_date"],
            "target_race_id": race["id"],
            "priority": priority,
        }
        r = api("POST", "/plans/generate", token=token, json=body)
        if r.status_code == 201:
            st.success("Plano gerado.")
            st.rerun()
        else:
            st.error(r.text)


def _expand_daily_button(token: str, plan_id: str, label: str, key: str) -> None:
    """Trigger the idempotent daily-expansion endpoint."""
    if st.button(label, key=key):
        r = api("POST", f"/plans/{plan_id}/expand", token=token)
        if r.status_code == 201:
            d = r.json()
            st.success(
                f"{d['days']} treinos gerados ({d['start']} → {d['end']}, "
                f"TSS total {d['tss_total']})."
            )
            st.rerun()
        else:
            st.error(r.text)


def plan_tab(token: str) -> None:
    _intelligence_summary(token)
    plan = _latest_plan(token)
    if not plan:
        st.subheader("📅 Plano de treino")
        st.info("Você ainda não tem um plano. Gere um abaixo para ver seu calendário de treinos.")
        _plan_generation_controls(token)
        return

    # The calendar is the star of the landing page.
    st.subheader("📅 Calendário de treinos")
    st.caption(
        f"{plan['name']} · {plan['total_weeks']} semanas · CTL inicial {plan.get('start_ctl')}"
    )

    wl = api("GET", f"/plans/{plan['id']}/workouts", token=token)
    daily = wl.json() if wl.status_code == 200 else []
    if daily:
        _render_calendar(token, daily, plan)
    else:
        st.info("Seu plano ainda não tem treinos diários.")
        _expand_daily_button(token, plan["id"], "Gerar treinos diários até a prova", "gen_daily")

    # Secondary detail, tucked below the calendar.
    with st.expander("📊 Periodização (semanas e blocos)"):
        weeks = sorted(plan.get("weeks", []), key=lambda w: w["week_index"])
        if weeks:
            df = pd.DataFrame([
                {"Semana": w["week_index"], "Início": w["week_start"], "Bloco": w["block_type"],
                 "TSS planejado": w["planned_tss"], "Foco": w.get("focus") or "",
                 "Deload": "🛌" if w.get("is_recovery_week") else ""}
                for w in weeks
            ])
            st.bar_chart(df.set_index("Início")[["TSS planejado"]])
            st.dataframe(df, hide_index=True, use_container_width=True)
        blocks = sorted(plan.get("blocks", []), key=lambda b: b["order_index"])
        if blocks:
            st.markdown("**Blocos:**")
            for b in blocks:
                st.write(f"- **{b['block_type']}**: {b['start_date']} → {b['end_date']} — {b.get('focus') or ''}")

    with st.expander("⚙️ Gerar ou regenerar plano"):
        _expand_daily_button(token, plan["id"], "Regenerar treinos diários até a prova", "regen_daily")
        st.divider()
        _plan_generation_controls(token)


def _render_calendar(token: str, daily: list[dict], plan: dict | None = None) -> None:
    by_date = {w["planned_date"]: w for w in daily}
    dates = sorted(by_date)
    plan_start = date.fromisoformat(dates[0])
    plan_end = date.fromisoformat(dates[-1])

    span_key = f"{dates[0]}_{dates[-1]}"
    if st.session_state.get("plan_span_key") != span_key:
        st.session_state["plan_span_key"] = span_key
        st.session_state["plan_week_offset"] = 0
        st.session_state.pop("plan_sel_date", None)

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

    nav1, nav2, nav3, _ = st.columns([1, 1, 1, 5])
    if nav1.button("◀ Semana"):
        st.session_state["plan_week_offset"] -= 1
        st.rerun()
    if nav2.button("Hoje"):
        st.session_state["plan_week_offset"] = 0
        st.rerun()
    if nav3.button("Semana ▶"):
        st.session_state["plan_week_offset"] += 1
        st.rerun()

    # Day selection drives the detail panel and the highlighted cell. A per-week
    # selectbox key keeps Streamlit from snapping the choice back on rerun and
    # lets us read the current selection before rendering the (static) grid.
    opts = [d.isoformat() for d in week if by_date.get(d.isoformat())]
    sel = None
    if opts:
        key = f"day_sel_{week[0].isoformat()}"
        if key not in st.session_state:
            st.session_state[key] = today.isoformat() if today.isoformat() in opts else opts[0]
        sel = st.session_state[key]

    block_label = cv.block_label_for_week((plan or {}).get("blocks", []), week)
    components.html(
        cv.calendar_html(week, by_date, completed, today, selected=sel,
                         block_label=block_label),
        height=cv.calendar_height(), scrolling=False,
    )

    if opts:
        sel = st.selectbox(
            "Ver treino do dia", opts, key=key,
            format_func=lambda iso: _day_option_label(iso, by_date),
        )
        _render_day_detail(token, by_date[sel], completed.get(sel, []), sel)


def _day_option_label(iso: str, by_date: dict) -> str:
    d = date.fromisoformat(iso)
    w = by_date.get(iso, {})
    wtype = cv.TYPE_LABEL.get(w.get("workout_type", ""), w.get("workout_type", ""))
    return f"{cv._WEEKDAYS_PT[d.weekday()]} {d.strftime('%d/%m')} · {w.get('name') or wtype}"


def _render_day_detail(token: str, w: dict, acts: list[dict], iso: str) -> None:
    st.divider()
    d = date.fromisoformat(iso)
    st.markdown(
        f"### {d.strftime('%d/%m')} · {w.get('name') or w['workout_type']}"
    )
    st.caption(
        f"{w['workout_type']} · {round((w.get('planned_duration_s') or 0) / 60)}min · "
        f"{round(w.get('planned_tss') or 0)} TSS"
    )
    detail = cv.detail_html(w.get("structure"))
    if detail:
        components.html(detail, height=cv.detail_height(), scrolling=False)
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

    if d >= date.today():
        st.divider()
        st.markdown("#### 🤖 Ajustar este treino com a IA")
        adj = w.get("adjustment")
        if adj:
            st.info(f"Treino ajustado pela IA · {round(adj.get('tss') or 0)} TSS. "
                    f"Motivo: {adj.get('reason') or '—'}")
            if st.button("↩️ Reverter para o planejado", key=f"revert_{w['id']}"):
                r = api("DELETE", f"/plans/workouts/{w['id']}/adjustment", token=token)
                st.rerun() if r.status_code == 200 else st.error(r.text)
        else:
            if st.button("Ajustar ao meu estado de hoje", key=f"adjust_{w['id']}"):
                r = api("POST", f"/plans/workouts/{w['id']}/adjust", token=token)
                if r.status_code == 201:
                    st.session_state[f"adjpreview_{w['id']}"] = r.json()
                else:
                    st.error(r.text)
            preview = st.session_state.get(f"adjpreview_{w['id']}")
            if preview:
                pl = preview.get("payload") or {}
                risk = preview["risk_level"]
                color = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🔴"}.get(risk, "⚪")
                st.markdown(f"**{color} Risco: {risk}** · {preview.get('summary')}")
                if pl.get("changed"):
                    st.caption(f"Ajustado: {round(pl.get('adjusted_tss') or 0)} TSS "
                               f"(planejado {round((pl.get('planned_snapshot') or {}).get('planned_tss') or 0)} TSS)")
                    detail = cv.detail_html(pl.get("adjusted_structure"))
                    if detail:
                        components.html(detail, height=cv.detail_height(), scrolling=False)
                else:
                    st.success("Seu estado está alinhado ao planejado — mantenha o treino.")
                st.write(preview.get("rationale"))
                fb_line = iv.feedback_line(((pl.get("signals")) or {}).get("feedback"))
                if fb_line:
                    st.caption(fb_line)
                c1, c2 = st.columns(2)
                if pl.get("changed") and c1.button("✅ Aceitar ajuste", key=f"acc_{w['id']}"):
                    a = api("POST", f"/plans/workouts/{w['id']}/apply-adjustment",
                            token=token, json={"recommendation_id": preview["id"]})
                    if a.status_code == 200:
                        st.session_state.pop(f"adjpreview_{w['id']}", None)
                        st.rerun()
                    else:
                        st.error(a.text)
                if c2.button("Manter planejado", key=f"keep_{w['id']}"):
                    api("POST", f"/recommendations/{preview['id']}/decision",
                        token=token, json={"decision": "REJECTED"})
                    st.session_state.pop(f"adjpreview_{w['id']}", None)
                    st.rerun()


def checkin_tab(token: str) -> None:
    st.subheader("📝 Check-in diário")
    st.caption("Como você está hoje? Isso ajusta a recomendação ao seu estado atual.")
    with st.form("checkin"):
        sleep_hours = st.number_input("Horas de sono", 0.0, 14.0, 7.0, step=0.5)
        resting_hr = st.number_input("FC repouso hoje", 30, 120, 55)
        hrv_ms = st.number_input("HRV (ms, opcional; 0 = não informar)", 0.0, 250.0, 0.0, step=1.0)
        fatigue = st.slider("Fadiga (1 ótimo – 5 exausto)", 1, 5, 3)
        soreness = st.slider("Dor muscular (1 – 5)", 1, 5, 2)
        mood = st.slider("Humor (1 – 5)", 1, 5, 4)
        motivation = st.slider("Motivação (1 – 5)", 1, 5, 4)
        injury_flag = st.checkbox("Dor/lesão hoje")
        comment = st.text_area("Comentário")
        if st.form_submit_button("Registrar check-in"):
            today = date.today().isoformat()
            rec = api("POST", "/metrics/recovery", token=token, json={
                "metric_date": today, "sleep_hours": sleep_hours,
                "resting_hr": int(resting_hr), "hrv_ms": hrv_ms or None,
            })
            sub = api("POST", "/metrics/subjective", token=token, json={
                "metric_date": today, "fatigue": fatigue, "soreness": soreness,
                "mood": mood, "motivation": motivation, "injury_flag": injury_flag,
                "comment": comment or None,
            })
            if rec.status_code == 201 and sub.status_code == 201:
                st.success("Check-in registrado. A próxima recomendação considerará seu estado de hoje.")
            else:
                st.error(f"recovery={rec.status_code} subjective={sub.status_code}")


_ANAMNESE_REQUIRED = (
    "birth_date", "sex", "weight_kg", "height_cm", "max_hr",
    "primary_discipline", "years_training", "goals", "weekly_hours",
)


def _anamnese_complete(profile: dict | None) -> bool:
    if not profile:
        return False
    return all(profile.get(f) not in (None, "") for f in _ANAMNESE_REQUIRED)


def anamnese_tab(token: str) -> None:
    st.subheader("🩺 Anamnese")
    st.caption("Preencha seu perfil — obrigatório para gerar recomendações personalizadas.")
    p = api("GET", "/athletes/me/profile", token=token)
    cur = (p.json() or {}) if p.status_code == 200 else {}
    sexes = ["M", "F", "Outro"]
    with st.form("anamnese"):
        birth = st.date_input(
            "Data de nascimento",
            value=date.fromisoformat(cur["birth_date"]) if cur.get("birth_date") else date(1990, 1, 1),
        )
        sex = st.selectbox("Sexo", sexes, index=sexes.index(cur["sex"]) if cur.get("sex") in sexes else 0)
        weight = st.number_input("Peso (kg)", 30.0, 200.0, float(cur.get("weight_kg") or 70.0), step=0.5)
        height = st.number_input("Altura (cm)", 120.0, 230.0, float(cur.get("height_cm") or 175.0), step=1.0)
        max_hr = st.number_input("FC máxima", 120, 230, int(cur.get("max_hr") or 185))
        resting_hr = st.number_input("FC repouso", 30, 120, int(cur.get("resting_hr") or 55))
        discipline = st.text_input("Disciplina principal (ex.: XCO, Maratona)", cur.get("primary_discipline") or "")
        years = st.number_input("Anos de treino", 0, 60, int(cur.get("years_training") or 1))
        goals = st.text_area("Objetivos", cur.get("goals") or "")
        weekly_hours = st.number_input("Disponibilidade (horas/semana)", 0.0, 40.0, float(cur.get("weekly_hours") or 6.0), step=0.5)
        weekly_days = st.number_input("Dias disponíveis/semana", 0, 7, int(cur.get("weekly_days") or 4))
        injury = st.text_area("Histórico de lesões/limitações", cur.get("injury_history") or "")
        medical = st.text_area("Condições médicas/medicações", cur.get("medical_conditions") or "")
        power = st.checkbox("Tenho medidor de potência", value=bool(cur.get("has_power_meter")))
        hrmon = st.checkbox("Tenho monitor de FC", value=bool(cur.get("has_hr_monitor")))
        if st.form_submit_button("Salvar anamnese"):
            body = {
                "birth_date": birth.isoformat(), "sex": sex, "weight_kg": weight, "height_cm": height,
                "max_hr": int(max_hr), "resting_hr": int(resting_hr),
                "primary_discipline": discipline or None, "years_training": int(years),
                "goals": goals or None, "weekly_hours": weekly_hours, "weekly_days": int(weekly_days),
                "injury_history": injury or None, "medical_conditions": medical or None,
                "has_power_meter": power, "has_hr_monitor": hrmon,
            }
            r = api("PUT", "/athletes/me/profile", token=token, json=body)
            if r.status_code == 200:
                st.success("Anamnese salva.")
                st.rerun()
            else:
                st.error(r.text)


def dashboard(token: str) -> None:
    me = api("GET", "/athletes/me", token=token).json()
    st.sidebar.success(f"Conectado: {me.get('full_name', '')}")
    if st.sidebar.button("Sair"):
        st.session_state.pop("token", None)
        st.rerun()

    _sample_workouts_sidebar(token)

    prof = api("GET", "/athletes/me/profile", token=token)
    profile = (prof.json() or {}) if prof.status_code == 200 else {}
    anamnese_ok = _anamnese_complete(profile)
    if not anamnese_ok:
        st.warning("Complete sua anamnese (aba 🩺 Anamnese) para liberar as recomendações.")

    tab_plan, tab_anamnese, tab_load, tab_import, tab_checkin, tab_races, tab_rec = st.tabs(
        ["📅 Plano", "🩺 Anamnese", "📈 Forma & Carga", "📥 Importar", "📝 Check-in", "🏁 Provas", "🧠 Recomendações"]
    )
    with tab_plan:
        plan_tab(token)
    with tab_anamnese:
        anamnese_tab(token)
    with tab_load:
        load_tab(token)
    with tab_import:
        import_tab(token)
    with tab_checkin:
        checkin_tab(token)
    with tab_races:
        races_tab(token)
    with tab_rec:
        recommendations_tab(token, anamnese_ok)


def admin_dashboard(token: str) -> None:
    st.sidebar.success("Treinador (admin)")
    if st.sidebar.button("Sair"):
        st.session_state.pop("token", None)
        st.rerun()

    st.title("📋 Painel do treinador — validação")

    usage = api("GET", "/admin/usage", token=token)
    u = usage.json() if usage.status_code == 200 else {}
    st.subheader("📊 Métricas da validação")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Atletas", u.get("athletes", 0))
    c2.metric("Treinos", u.get("workouts", 0))
    c3.metric("Recomendações", u.get("recommendations", 0))
    c4.metric("Feedbacks", u.get("feedback_count", 0))
    c5.metric("Nota média", f"{u.get('avg_feedback_rating', 0):.1f}")

    ath_resp = api("GET", "/admin/athletes", token=token)
    athletes = ath_resp.json() if ath_resp.status_code == 200 else []
    names = {a["id"]: a["full_name"] for a in athletes}

    st.subheader("👥 Atletas")
    if athletes:
        st.dataframe(pd.DataFrame([
            {"Nome": a["full_name"], "Email": a["email"],
             "Ativo": "✅" if a.get("is_active") else "—"}
            for a in athletes
        ]), hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum atleta.")

    st.subheader("💬 Feedbacks")
    fb_resp = api("GET", "/admin/feedback", token=token)
    feedbacks = fb_resp.json() if fb_resp.status_code == 200 else []
    if feedbacks:
        st.dataframe(pd.DataFrame([
            {"Atleta": names.get(f.get("athlete_id"), str(f.get("athlete_id"))[:8]),
             "Nota": f.get("rating"),
             "Fez sentido": "✅" if f.get("made_sense") else "—",
             "Comentário": f.get("comment") or "",
             "Data": (f.get("created_at") or "")[:10]}
            for f in feedbacks
        ]), hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum feedback ainda.")


def main() -> None:
    token = st.session_state.get("token")
    if not token:
        login_view()
        return
    resp = api("GET", "/athletes/me", token=token)
    if resp.status_code != 200:
        # Expired/invalid token — clear it and fall back to login.
        st.session_state.pop("token", None)
        login_view()
        return
    me = resp.json()
    if me.get("role") == "ADMIN":
        admin_dashboard(token)
    else:
        dashboard(token)


if __name__ == "__main__":
    main()
