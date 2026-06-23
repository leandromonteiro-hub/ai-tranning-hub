# Design — Loop self-service na UI (provas → plano → recomendação ciente da fase)

**Data:** 2026-06-23
**Status:** Aprovado
**Fase do projeto:** Fase 0 — validação com 2 atletas
**Camada:** Frontend (Streamlit) — sem mudanças de backend

---

## 1. Motivação

O backend já suporta provas, planos periodizados, métricas e curva de potência, mas o
frontend Streamlit só expõe login, importação, gráfico de carga e recomendações. Falta
crítica: o atleta **não consegue cadastrar uma prova nem gerar um plano pela UI**, então a
recomendação diária sempre cai no bloco **BASE** padrão (a recomendação só fica específica da
fase quando existe um `TrainingWeek` cobrindo a data — ver `TrainingWeekRepository.block_on`).

Objetivo: fechar o loop self-service na interface para que cada atleta rode a validação de 4
semanas sozinho — **cadastrar prova → gerar plano → ver o plano → recomendação ciente da fase
→ executar → feedback**.

## 2. Fronteira

**Em escopo (só frontend, `frontend/app.py`):**
- Aba **Provas**: criar (`POST /races`) e listar (`GET /races`).
- Aba **Plano**: gerar (`POST /plans/generate`) e visualizar plano (tabela de semanas + gráfico
  + blocos), listar planos (`GET /plans`).
- Melhoria na aba **Recomendações**: mostrar a fase/semana atual do plano antes de gerar.

**Fora de escopo (YAGNI):** editar/excluir prova ou plano; resultados de prova
(`POST /races/results`); análises pré/pós (`/races/analyses`); painel admin; seleção entre
múltiplos planos ativos; backend (todos os endpoints já existem e estão testados).

## 3. Endpoints consumidos (já existentes)

| Ação | Método | Campos relevantes |
|---|---|---|
| Criar prova | `POST /api/v1/races` | `name`, `race_date`, `discipline?`, `priority` (A/B/C), `location?`, `distance_km?`, `elevation_gain_m?`, `notes?` |
| Listar provas | `GET /api/v1/races` | retorna ordenado por `race_date`; cada item tem `id`, `name`, `race_date`, `priority`, ... |
| Gerar plano | `POST /api/v1/plans/generate` | `name`, `race_date`, `target_race_id?`, `priority` (A/B/C), `start_date?` |
| Listar planos | `GET /api/v1/plans` | cada plano tem `id`, `name`, `start_date`, `race_date`, `total_weeks`, `blocks[]`, `weeks[]` |

`TrainingWeekRead`: `week_index`, `week_start`, `block_type`, `planned_tss`, `executed_tss?`,
`is_recovery_week`, `focus?`. `TrainingBlockRead`: `block_type`, `order_index`, `start_date`,
`end_date`, `focus?`.

## 4. Componentes (UI)

Todas as abas usam o helper `api(method, path, token=, **kwargs)` existente (httpx + JWT,
tenant-scoped pelo token). Estados vazios sempre tratados.

### 4.1 Aba "🏁 Provas"
- `st.form` com: `name` (texto), `race_date` (date_input), `discipline` (texto, opcional —
  ex.: XCO/Maratona), `priority` (selectbox A/B/C), e um expander "Mais detalhes" com
  `location`, `distance_km`, `elevation_gain_m`, `notes`.
- Ao enviar: `POST /races`; sucesso → `st.success` + `st.rerun()`; erro → `st.error(resp.text)`.
- Abaixo, lista de provas (`GET /races`) numa tabela (data, nome, prioridade, disciplina),
  ordenada por data. Vazio → `st.info("Nenhuma prova cadastrada ainda.")`.

### 4.2 Aba "📅 Plano"
- **Gerar plano**: selectbox de provas cadastradas (rótulo `"<data> — <nome> (P<priority>)"`)
  → preenche `name`, `race_date`, `target_race_id`, `priority` a partir da prova escolhida;
  botão **"Gerar plano"** chama `POST /plans/generate`. Se não houver prova, instruir a
  cadastrar na aba Provas (sem caminho avulso, para manter o loop coeso — YAGNI).
- **Visualizar**: pega o plano mais recente de `GET /plans` (maior `start_date`). Mostra:
  - cabeçalho: nome, prova-alvo, `total_weeks`, CTL inicial;
  - **gráfico de barras** do `planned_tss` por semana (`st.bar_chart` indexado por `week_start`);
  - **tabela** semana-a-semana: semana, início, **bloco**, TSS planejado, foco, deload (🛌);
  - **resumo dos blocos** (`blocks[]`): tipo, período (início–fim), foco.
- Vazio → `st.info("Nenhum plano ainda. Gere um acima para uma prova.")`.

### 4.3 Aba "🧠 Recomendações" (melhoria)
- Antes do botão "Gerar recomendação", computar no frontend a fase do dia a partir do plano
  mais recente: a `TrainingWeek` cujo `[week_start, week_start+7dias)` contém `date.today()`.
  Exibir `st.info("Hoje: fase **{block_type}** · semana {week_index}/{total_weeks}")` quando
  houver; senão `st.caption("Sem plano ativo — a recomendação usará o bloco padrão (BASE).")`.
- Restante do fluxo (gerar → estrutura → download `.fit`/`.zwo` → feedback) inalterado.

## 5. Organização do código

`frontend/app.py` cresce de ~200 para ~350 linhas. Refatorar em funções por aba para manter
cada unidade focada: `load_tab(token)`, `import_tab(token)`, `races_tab(token)`,
`plan_tab(token)`, `recommendations_tab(token)`, com helpers pequenos
(`_current_phase(plan)`, `_fmt_race_label(race)`). `dashboard(token)` apenas monta as abas e
delega. Se o arquivo passar de ~400 linhas, dividir em módulos `frontend/views/`.

## 6. Tratamento de erros e estados
- Toda chamada de escrita confere `status_code` (201/200) e mostra `resp.text` em falha.
- Leituras com fallback a lista vazia quando `status_code != 200`.
- `st.rerun()` após criação para refrescar listas.

## 7. Testes e verificação
- Sem testes automatizados de UI (padrão do projeto; o backend de provas/planos já é coberto
  por `app/tests/test_api/test_app.py::test_race_calendar_and_plan_generation`).
- **Verificação ao vivo (gate de aceitação):** no Streamlit (athlete1), (a) cadastrar uma prova
  ~12 semanas à frente; (b) gerar o plano e ver o calendário com blocos base→build→peak→taper;
  (c) abrir Recomendações e confirmar que a fase/semana do dia aparece; (d) gerar a recomendação
  e confirmar que o `block_relation`/conteúdo reflete a fase (não mais BASE genérico).
- Checagem de sintaxe do `app.py` (`ast.parse`) antes do commit.

## 8. Riscos
| Risco | Mitigação |
|---|---|
| Plano gerado com início no passado não cobre "hoje" | Default `start_date` = hoje (já é o default do backend); a prova deve ser futura |
| `app.py` ficando grande/confuso | Refatoração em funções por aba; limite de ~400 linhas para dividir |
| Plano não cobre a data de hoje (prova muito próxima) | `_current_phase` retorna None → cai no aviso "bloco padrão"; comportamento correto |
