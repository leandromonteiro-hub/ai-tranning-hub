# Design — Personalização: anamnese + check-in de prontidão

**Data:** 2026-06-23
**Status:** Aprovado
**Fase do projeto:** Fase 0 — validação com 2 atletas
**Camadas:** Backend (modelo + migração + prompt + gate) + Frontend (2 abas + gate)

---

## 1. Motivação

A recomendação hoje é genérica: usa CTL/ATL/TSB + histórico + FTP, mas **não conhece quem é o
atleta** (idade, experiência, objetivos, limitações) nem **o estado do dia** de forma coletada.
O backend já tem a infraestrutura (`AthleteProfile` + `GET/PUT /athletes/me/profile`;
`SubjectiveMetric`/`RecoveryMetric` + `POST /metrics/subjective|recovery`; o Digital Twin já
consome fadiga/sono/HRV/lesão), mas: (a) não há UI para coletar; (b) o perfil não chega ao prompt
do LLM; (c) o perfil é fino. Objetivo: coletar anamnese (obrigatória) + check-in diário, e
**injetar o perfil na IA** para personalizar.

## 2. Fronteira

**Em escopo:** enriquecer `AthleteProfile`; injetar resumo do perfil no prompt; gate de
anamnese (409) em `POST /recommendations`; aba Anamnese (onboarding gate); aba Check-in diário.

**Fora de escopo (YAGNI):** alterar a lógica dos guardrails com base em idade/FC; zonas de FC
personalizadas; edição do perfil de terceiros pelo admin; histórico clínico estruturado além de
texto livre.

## 3. Backend

### 3.1 Enriquecer `AthleteProfile` (migração `0004`)
Campos atuais: `birth_date, sex, height_cm, weight_kg, max_hr, resting_hr, primary_discipline,
years_training, notes`. **Adicionar (todos nullable):**
- `goals: Text` — objetivos do atleta
- `weekly_hours: Float` — disponibilidade semanal (horas)
- `weekly_days: Integer` — dias/semana disponíveis
- `injury_history: Text` — histórico de lesões/limitações
- `medical_conditions: Text` — condições médicas/medicações relevantes
- `has_power_meter: Boolean` (default False)
- `has_hr_monitor: Boolean` (default False)

Atualizar `AthleteProfileBase` (e portanto `AthleteProfileUpdate`/`AthleteProfileRead`) com os
mesmos campos. Migração `0004` adiciona as colunas (nullable / default) à tabela
`athlete_profiles`; a conftest (SQLite) cria a tabela a partir de `Base.metadata` (já inclui os
campos novos), então testes não dependem da migração.

### 3.2 Injetar o perfil no prompt
Helper `profile_summary(profile) -> str` (em `app/services/ai/`) que monta uma linha legível:
ex. `"34a, M, 72kg, 178cm, FCmáx 188, FCrep 52, 6 anos, MTB · Objetivos: ... · Disponib.:
8h/4d · Lesões: ... · Condições: ... · Equip.: potência sim, FC sim"`. Campos ausentes viram
"n/d". O recomendador busca o `AthleteProfile` (tenant-scoped) e passa o resumo ao template
versionado de prompt (novo slot `{profile}` em `prompts.DAILY_WORKOUT_TEMPLATE` /
`render_daily_workout(..., profile=...)`). Sem perfil → `"n/d"` (mas o gate bloqueia antes).

### 3.3 Gate de anamnese
Helper `anamnese_complete(profile) -> bool`: True quando o perfil existe e tem **todos** os
obrigatórios não-nulos: `birth_date, sex, weight_kg, height_cm, max_hr, primary_discipline,
years_training, goals, weekly_hours`. (`resting_hr`, `injury_history`, `medical_conditions`,
`has_power_meter`, `has_hr_monitor` são recomendados, não bloqueiam.)
`POST /recommendations`: se a anamnese não estiver completa, retornar **HTTP 409** com
`detail="Anamnese incompleta — complete seu perfil antes de gerar recomendações."` (checado no
início do handler, antes de gerar). Demais endpoints inalterados.

## 4. Frontend (`frontend/app.py`)

### 4.1 Aba "🩺 Anamnese" + gate de onboarding
- Form com todos os campos do perfil (`GET /athletes/me/profile` para pré-preencher,
  `PUT /athletes/me/profile` para salvar). Obrigatórios marcados; ao salvar incompleto, avisar.
- **Gate:** em `dashboard(token)`, buscar o perfil; se `anamnese_complete` for falso (mesma
  regra do backend, replicada no front), abrir o dashboard já com foco na aba Anamnese e exibir
  um aviso no topo ("Complete sua anamnese para liberar as recomendações."). A aba Recomendações,
  se a anamnese estiver incompleta (ou o backend devolver 409), mostra a mesma orientação em vez
  do botão de gerar.

### 4.2 Aba "🩺 Check-in diário"
- Form de prontidão (data = hoje): `sleep_hours`, `resting_hr`, `hrv_ms` (opcional) →
  `POST /metrics/recovery`; `mood`, `fatigue`, `motivation`, `soreness` (1–5), `injury_flag`
  (checkbox), `comment` → `POST /metrics/subjective`. Um único botão "Registrar check-in" envia
  ambos.
- Mostrar os últimos check-ins (`GET /metrics/recovery` + `/metrics/subjective` recentes, se os
  endpoints de leitura existirem; senão, apenas confirmar o envio). O Digital Twin já consome
  esses dados, então a próxima recomendação reflete o estado.

> Verificar no plano se há `GET` para recovery/subjective; se não houver, o check-in apenas
> registra (POST) e confia no twin — sem listagem (YAGNI; não criar endpoints novos só p/ listar).

## 5. Dados, erros, estados
- Leituras no front com fallback; estados vazios via `st.info`; `st.rerun()` após salvar.
- Backend: 409 no gate; escrita de check-in retorna 201 (já existente).

## 6. Testes e verificação
- **Backend (pytest):** (a) colunas novas presentes (perfil aceita os campos via PUT e os
  devolve); (b) gate: `POST /recommendations` → 409 sem anamnese, 201 após PUT completo;
  (c) injeção: após anamnese completa, `LlmCallLog.prompt` (ou o prompt renderizado) contém o
  resumo do perfil. Soma à suíte (73).
- **Frontend:** `ast.parse` + shakedown ao vivo: preencher anamnese (gate libera) → check-in →
  gerar recomendação e conferir que o texto reflete perfil/estado.

## 7. Riscos
| Risco | Mitigação |
|---|---|
| Atletas de teste do seed sem anamnese → 409 ao gerar rec | Esperado; preencher a anamnese é o 1º passo do fluxo. Documentar no runbook. |
| Regra de "completo" divergir entre back e front | Mesma lista de campos obrigatórios nos dois; fonte única documentada aqui (§3.3). |
| Mudança no template de prompt versionado | Novo slot `{profile}`; bump de versão do template se o store de prompts versionar por hash. |
| Migração em coluna de tabela populada | Colunas nullable/default → seguro em tabela com dados. |
