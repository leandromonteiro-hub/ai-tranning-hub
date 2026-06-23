"""Athlete AI Training Hub — Streamlit validation UI.

Minimal, purpose-built for the 2-athlete validation: log in, import history,
see the CTL/ATL/TSB chart, request a recommendation, and give feedback. Chosen
over Next.js for the MVP because it ships a working feedback loop in one Python
codebase with near-zero frontend overhead.
"""
from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st

API = os.environ.get("STREAMLIT_API_BASE_URL", "http://localhost:8000/api/v1")

st.set_page_config(page_title="Athlete AI Training Hub", layout="wide")


def api(method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.request(method, f"{API}{path}", headers=headers, timeout=30, **kwargs)


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


def dashboard(token: str) -> None:
    me = api("GET", "/athletes/me", token=token).json()
    st.sidebar.success(f"Conectado: {me.get('full_name', '')}")
    if st.sidebar.button("Sair"):
        st.session_state.pop("token", None)
        st.rerun()

    with st.sidebar.expander("🧪 Treinos de teste (.fit)"):
        st.caption("Baixe um treino estruturado de exemplo para testar a importação no device.")
        ftp = st.number_input("FTP (W)", min_value=80, max_value=600, value=250, step=5)
        samples = [
            ("Sweet Spot 3×12", "sweet_spot"),
            ("VO2max 5×4", "vo2max"),
            ("Endurance Z2", "endurance"),
            ("Recuperação Z1", "recovery"),
        ]
        for label, template in samples:
            resp = api("GET", "/recommendations/sample.fit", token=token,
                       params={"template": template, "ftp": ftp})
            if resp.status_code == 200:
                st.download_button(
                    f"⬇️ {label}",
                    data=resp.content,
                    file_name=f"{template}_ftp{int(ftp)}.fit",
                    mime="application/octet-stream",
                    key=f"sample_{template}",
                )

    tab_load, tab_import, tab_rec = st.tabs(
        ["📈 Forma & Carga", "📥 Importar", "🧠 Recomendações"]
    )

    with tab_load:
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

    with tab_import:
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

    with tab_rec:
        st.subheader("Recomendação de treino")
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

            has_structured = bool((rec.get("payload") or {}).get("structured_workout"))
            if has_structured:
                fit_resp = api("GET", f"/recommendations/{rec['id']}/export.fit", token=token)
                if fit_resp.status_code == 200:
                    st.download_button(
                        "⬇️ Baixar treino (.fit)",
                        data=fit_resp.content,
                        file_name=f"treino_{rec['id'][:8]}.fit",
                        mime="application/octet-stream",
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


def main() -> None:
    token = st.session_state.get("token")
    if not token:
        login_view()
    else:
        dashboard(token)


if __name__ == "__main__":
    main()
