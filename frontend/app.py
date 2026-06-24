"""Athlete AI Training Hub — Streamlit validation UI.

Minimal, purpose-built for the 2-athlete validation: log in, import history,
set a target race, generate a periodized plan, request a phase-aware
recommendation, and give feedback. Chosen over Next.js for the MVP because it
ships a working feedback loop in one Python codebase with near-zero overhead.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import httpx
import pandas as pd
import streamlit as st

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


def load_tab(token: str) -> None:
    st.subheader("CTL (fitness) · ATL (fadiga) · TSB (forma)")
    if st.button("Recalcular métricas"):
        api("POST", "/metrics/load/recompute", token=token)
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
        if resp.status_code == 200:
            st.success("Importação concluída")
            st.dataframe(pd.DataFrame(resp.json()))
        else:
            st.error(resp.text)


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


def plan_tab(token: str) -> None:
    st.subheader("Plano de treino periodizado")
    resp = api("GET", "/races", token=token)
    races = resp.json() if resp.status_code == 200 else []
    if races:
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
            resp = api("POST", "/plans/generate", token=token, json=body)
            if resp.status_code == 201:
                st.success("Plano gerado.")
                st.rerun()
            else:
                st.error(resp.text)
    else:
        st.info("Cadastre uma prova na aba Provas para gerar um plano.")

    plan = _latest_plan(token)
    if not plan:
        st.info("Nenhum plano ainda. Gere um acima.")
        return

    st.markdown(
        f"**{plan['name']}** · {plan['total_weeks']} semanas · "
        f"CTL inicial: {plan.get('start_ctl')}"
    )
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

    tab_anamnese, tab_load, tab_import, tab_checkin, tab_races, tab_plan, tab_rec = st.tabs(
        ["🩺 Anamnese", "📈 Forma & Carga", "📥 Importar", "📝 Check-in", "🏁 Provas", "📅 Plano", "🧠 Recomendações"]
    )
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
    with tab_plan:
        plan_tab(token)
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
