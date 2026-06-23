# Self-Service Loop UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar o loop self-service no frontend Streamlit — atleta cadastra prova, gera plano periodizado, vê o plano, e a recomendação diária mostra/usa a fase do dia.

**Architecture:** Só frontend (`frontend/app.py`). O backend já expõe `POST/GET /races` e `POST /plans/generate` + `GET /plans`, e a recomendação já fica ciente do bloco quando existe um plano cobrindo a data. Refatorar `app.py` em funções por aba e adicionar as abas Provas e Plano + o indicador de fase.

**Tech Stack:** Streamlit, httpx (via helper `api()`), pandas. Sem testes automatizados de UI (padrão do projeto) — verificação por checagem de sintaxe (`ast.parse`) + shakedown ao vivo no Streamlit (stack já no ar em http://localhost:8501).

## Global Constraints

- **Só frontend.** Nenhuma mudança em backend/migrações. Todos os endpoints já existem e são tenant-scoped pelo JWT.
- **Helper `api(method, path, token=None, **kwargs)`** já existe — toda chamada usa ele.
- **Prioridade** é sempre uma de `A`/`B`/`C` (o backend valida `^[ABC]$`).
- **Datas** enviadas como ISO (`date.isoformat()`).
- **Estados vazios** sempre tratados com `st.info(...)`.
- **Sem testes de UI**: cada task verifica com `ast.parse` + checagem manual ao vivo. Comando de sintaxe (da raiz do repo):
  `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); print('syntax OK')"`
- **Ordem final das abas:** `📈 Forma & Carga`, `📥 Importar`, `🏁 Provas`, `📅 Plano`, `🧠 Recomendações`.
- Commits frequentes, um por task.

---

### Task 1: Refatorar `app.py` em funções por aba (preserva comportamento)

**Files:**
- Modify (rewrite): `frontend/app.py`

**Interfaces:**
- Produces: `login_view()`, `api(...)` (inalterado), `_sample_workouts_sidebar(token)`, `load_tab(token)`, `import_tab(token)`, `recommendations_tab(token)`, `dashboard(token)`, `main()`.

- [ ] **Step 1: Reescrever `frontend/app.py`** com o conteúdo abaixo (mesmo comportamento das 3 abas atuais + seção de teste no sidebar, apenas reorganizado em funções):

```python
"""Athlete AI Training Hub — Streamlit validation UI.

Minimal, purpose-built for the 2-athlete validation: log in, import history,
set a target race, generate a periodized plan, request a phase-aware
recommendation, and give feedback. Chosen over Next.js for the MVP because it
ships a working feedback loop in one Python codebase with near-zero overhead.
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


def recommendations_tab(token: str) -> None:
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


def dashboard(token: str) -> None:
    me = api("GET", "/athletes/me", token=token).json()
    st.sidebar.success(f"Conectado: {me.get('full_name', '')}")
    if st.sidebar.button("Sair"):
        st.session_state.pop("token", None)
        st.rerun()

    _sample_workouts_sidebar(token)

    tab_load, tab_import, tab_rec = st.tabs(
        ["📈 Forma & Carga", "📥 Importar", "🧠 Recomendações"]
    )
    with tab_load:
        load_tab(token)
    with tab_import:
        import_tab(token)
    with tab_rec:
        recommendations_tab(token)


def main() -> None:
    token = st.session_state.get("token")
    if not token:
        login_view()
    else:
        dashboard(token)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Checar sintaxe**

Run (da raiz do repo):
`docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); print('syntax OK')"`
Expected: `syntax OK`

- [ ] **Step 3: Verificação ao vivo**

Abrir http://localhost:8501, logar (`athlete1@athletehub.example.com` / `athlete1_pwd`), confirmar que as 3 abas (Forma & Carga, Importar, Recomendações) e a seção "🧪 Treinos de teste" do sidebar funcionam como antes.
Expected: comportamento idêntico ao anterior.

- [ ] **Step 4: Commit**

```bash
git add frontend/app.py
git commit -m "refactor(frontend): organize Streamlit dashboard into per-tab functions"
```

---

### Task 2: Aba "🏁 Provas" (cadastrar + listar)

**Files:**
- Modify: `frontend/app.py`

**Interfaces:**
- Consumes: `api(...)`, `dashboard(token)` da Task 1.
- Produces: `races_tab(token)`; `dashboard` passa a montar a aba Provas.

- [ ] **Step 1: Adicionar `races_tab`** — inserir esta função imediatamente antes de `def dashboard(token: str) -> None:` em `frontend/app.py`:

```python
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
```

- [ ] **Step 2: Montar a aba** — em `dashboard(token)`, substituir o bloco de tabs por:

```python
    tab_load, tab_import, tab_races, tab_rec = st.tabs(
        ["📈 Forma & Carga", "📥 Importar", "🏁 Provas", "🧠 Recomendações"]
    )
    with tab_load:
        load_tab(token)
    with tab_import:
        import_tab(token)
    with tab_races:
        races_tab(token)
    with tab_rec:
        recommendations_tab(token)
```

- [ ] **Step 3: Checar sintaxe**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); print('syntax OK')"`
Expected: `syntax OK`

- [ ] **Step 4: Verificação ao vivo**

Na aba "🏁 Provas": cadastrar uma prova (nome + data ~12 semanas à frente + prioridade A) → aparece "Prova cadastrada" e ela surge na lista abaixo.
Expected: criação 201 + prova listada por data.

- [ ] **Step 5: Commit**

```bash
git add frontend/app.py
git commit -m "feat(frontend): races tab (create + list target races)"
```

---

### Task 3: Aba "📅 Plano" (gerar + visualizar) + helpers de plano

**Files:**
- Modify: `frontend/app.py`

**Interfaces:**
- Consumes: `api(...)`, `dashboard(token)`.
- Produces: `_fmt_race_label(r)`, `_latest_plan(token)`, `_current_phase(plan)`, `plan_tab(token)`. `_latest_plan`/`_current_phase` são reusados pela Task 4.

- [ ] **Step 1: Adicionar import de datas** — em `frontend/app.py`, logo após `import os`, adicionar:

```python
from datetime import date, timedelta
```

- [ ] **Step 2: Adicionar helpers + `plan_tab`** — inserir imediatamente antes de `def dashboard(token: str) -> None:`:

```python
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
    races = api("GET", "/races", token=token).json() or []
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
```

- [ ] **Step 3: Montar a aba** — em `dashboard(token)`, substituir o bloco de tabs por:

```python
    tab_load, tab_import, tab_races, tab_plan, tab_rec = st.tabs(
        ["📈 Forma & Carga", "📥 Importar", "🏁 Provas", "📅 Plano", "🧠 Recomendações"]
    )
    with tab_load:
        load_tab(token)
    with tab_import:
        import_tab(token)
    with tab_races:
        races_tab(token)
    with tab_plan:
        plan_tab(token)
    with tab_rec:
        recommendations_tab(token)
```

- [ ] **Step 4: Checar sintaxe**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); print('syntax OK')"`
Expected: `syntax OK`

- [ ] **Step 5: Verificação ao vivo**

Na aba "📅 Plano": selecionar a prova cadastrada na Task 2 → "Gerar plano" → aparece o cabeçalho do plano, o gráfico de TSS por semana, a tabela semana-a-semana com blocos (base→build→peak→taper) e o resumo de blocos.
Expected: plano gerado (201) e visualizado com as fases.

- [ ] **Step 6: Commit**

```bash
git add frontend/app.py
git commit -m "feat(frontend): plan tab (generate + visualize periodized plan)"
```

---

### Task 4: Indicador de fase do dia na aba Recomendações

**Files:**
- Modify: `frontend/app.py`

**Interfaces:**
- Consumes: `_latest_plan(token)`, `_current_phase(plan)` da Task 3.
- Produces: `recommendations_tab` mostra a fase/semana atual antes de gerar.

- [ ] **Step 1: Inserir o indicador** — em `recommendations_tab(token)`, logo após a linha `st.subheader("Recomendação de treino")`, inserir:

```python
    _plan = _latest_plan(token)
    _phase = _current_phase(_plan) if _plan else None
    if _phase:
        st.info(f"Hoje: fase **{_phase['block_type']}** · semana {_phase['week_index']}/{_plan['total_weeks']}")
    else:
        st.caption("Sem plano ativo cobrindo hoje — a recomendação usará o bloco padrão (BASE).")
```

- [ ] **Step 2: Checar sintaxe**

Run: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); print('syntax OK')"`
Expected: `syntax OK`

- [ ] **Step 3: Verificação ao vivo (gate de aceitação do loop)**

Com a prova (Task 2) e o plano (Task 3) criados: abrir "🧠 Recomendações" → aparece "Hoje: fase **X** · semana N/total". Gerar a recomendação e confirmar no texto/`block_relation` que reflete a fase (não mais BASE genérico, salvo se hoje realmente cair em BASE). Sem plano cobrindo hoje, aparece o aviso de bloco padrão.
Expected: fase do dia exibida e recomendação coerente com a fase.

- [ ] **Step 4: Commit**

```bash
git add frontend/app.py
git commit -m "feat(frontend): show today's training phase in recommendations tab"
```

---

## Self-Review (autor do plano)

- **Cobertura do spec:** §4.1 Provas → Task 2; §4.2 Plano → Task 3; §4.3 fase do dia → Task 4; §5 organização em funções → Task 1; §7 verificação ao vivo → steps de verificação em cada task (gate em Task 4). Ordem de abas (Global Constraints) batida em Task 3.
- **Placeholders:** nenhum; cada step traz o código completo e comandos exatos.
- **Consistência de tipos/nomes:** `_latest_plan`/`_current_phase`/`_fmt_race_label` definidos na Task 3 e usados na Task 4; `races_tab`/`plan_tab`/`recommendations_tab`/`load_tab`/`import_tab`/`_sample_workouts_sidebar` consistentes entre Task 1 e o `dashboard`; `date`/`timedelta` importados na Task 3 antes do uso.
