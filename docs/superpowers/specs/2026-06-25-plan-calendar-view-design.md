# Calendário de Treinos (visualização profissional estilo TrainingPeaks) — Design Spec

**Data:** 2026-06-25
**Branch:** `feat/daily-plan-expansion`
**Status:** aprovado pelo usuário (aguardando review do spec escrito)

## Problema

A visualização atual da aba 📅 Plano (tabela plana de dias + barras de TSS) é considerada "horrível" pelo usuário. Precisamos de uma visualização profissional, lúdica, no padrão TrainingPeaks: um **calendário semanal** onde cada dia mostra o treino com o **perfil em degraus colorido por zona** ("quadrados dos intervalos"), com **overlay planejado × realizado**.

## Decisões tomadas (brainstorming)

1. **Layout:** vista **semanal** (7 colunas Seg–Dom, células ricas), com navegação entre semanas. (Padrão TrainingPeaks.)
2. **Interação ao selecionar um dia:** abre **painel de detalhe abaixo** do calendário com perfil grande, lista de intervalos, stats e download .zwo/.fit.
3. **Escopo:** **planejado + realizado (overlay)** por dia.
4. **Fidelidade do realizado:** **resumo de adesão** (selo: ✓ feito, TSS real vs planejado, duração, IF, cor de adesão). Curva real por-segundo (streams) fica para v2.
5. **Abordagem de renderização:** **A — Streamlit nativo + Altair** (Altair já é dependência do frontend). Descartadas: HTML/SVG custom (frágil, downloads difíceis) e streamlit-calendar/FullCalendar (não desenha perfil de intervalos na célula).
6. **Tela atual:** **remover** a tabela plana de dias (adicionada na Task 5 anterior); **manter** o gráfico de barras de TSS por semana + resumo de blocos; o botão "Gerar treinos diários até a prova" permanece.

## Arquitetura

### Backend (mudança mínima)
- **Modificar** `app/schemas/planning.py` → `PlannedWorkoutRead` ganha `name: str` e `structure: dict | None`. A rota `GET /plans/{plan_id}/workouts` já retorna as linhas `WorkoutPlanned`; só alargamos o schema para expor a estrutura (necessária para desenhar o perfil) e o nome.
- **Realizado:** reusar `GET /workouts?start=&end=` (já existe, `WorkoutCompletedRead`: `workout_date`, `workout_type`, `duration_s`, `tss`, `intensity_factor`, `normalized_power`, ...). **Nenhuma rota nova.**

### Frontend — novo módulo `frontend/calendar_view.py`
Separa a lógica de calendário do `app.py` (que já está grande). Contém:

**Funções puras (sem `streamlit`/`altair` no topo do módulo → unit-testáveis em container slim):**
- `flatten_structure(structure: dict) -> list[dict]` — expande `elements` (Step | Repeat) numa lista plana de segmentos `{intensity, duration_s, low, high}` (low/high em fração de FTP). `Repeat` é expandido `count` vezes. Estrutura ausente/malformada → `[]`.
- `ZONE_COLORS: dict[int, str]`, `ZONE_NAMES: dict[int, str]`, `zone_of(pct: float) -> int` — classificação Coggan de 7 zonas pelo %FTP (usa o ponto médio de low/high; `open`/sem target → zona 2 por padrão).
- `interval_lines(structure: dict) -> list[str]` — texto legível por elemento; `Repeat` colapsa em `"N× <on> / <off>"`. Ex.: `"Aquecimento 15min @ 60%"`, `"3× 5min @ 115% / 3min @ 50%"`, `"Volta calma 10min @ 55%"`.
- `adherence(plan_tss: float | None, actual_tss: float | None) -> tuple[str, str]` — `(emoji_cor, rótulo)`. Verde `✅` se `actual >= 0.9*plan`; amarelo `🟡` se `0.5*plan <= actual < 0.9*plan`; vermelho `🔴` se `actual < 0.5*plan`. Sem planejado ou sem realizado → `("", "")`.

**Render (importa `altair` preguiçosamente dentro da função para não exigir altair nos testes):**
- `profile_chart(segments: list[dict], *, mini: bool = True)` — `alt.Chart` de área em degraus (`mark_area(interpolate="step-after")`), x = minutos acumulados, y = %FTP, `color` por zona (escala categórica com paleta fixa `ZONE_COLORS`). `mini=True`: sem eixos/legenda, altura pequena (célula). `mini=False`: com eixos e bandas de zona (painel de detalhe). `segments == []` → retorna `None` (caller mostra só rótulos). **Nota de implementação:** Implementado com `mark_bar` (barras em degraus de 0 até %FTP), não `mark_area`; segmento `open`→0.45 (zona 1). O plano de implementação é a referência canônica.

### Zonas (Coggan, por %FTP)
| Zona | Nome | Faixa %FTP | Cor (sugestão) |
|------|------|-----------|----------------|
| 1 | Recuperação | < 56% | cinza |
| 2 | Endurance | 56–75% | azul |
| 3 | Tempo | 76–90% | verde |
| 4 | Limiar | 91–105% | amarelo |
| 5 | VO2max | 106–120% | laranja |
| 6 | Anaeróbico | 121–150% | vermelho |
| 7 | Neuromuscular | > 150% | roxo |

(Cores exatas a confirmar na implementação; manter consistência com a paleta usada em qualquer visual existente.)

### Integração no `plan_tab` (`frontend/app.py`) + estado
- **Estado de navegação:** `st.session_state["plan_week_offset"]` (int, default = semana que contém hoje, dentro do intervalo do plano). Botões ◀ / **Hoje** / ▶; clamp ao intervalo do plano. Rótulo: intervalo de datas da semana + TSS (plan vs real).
- **Grade:** `st.columns(7)` (Seg–Dom). Cada célula:
  - cabeçalho: dia da semana + data (destaque para "hoje");
  - se há treino planejado: mini `profile_chart` + tipo + `plan TSS`;
  - se dia passado **e** há realizado: selo de adesão (`adherence`) colorido + `TSS real · duração · IF`;
  - dia de descanso (sem planejado): rótulo "descanso";
  - `st.button(key=f"day_{iso_date}")` seleciona o dia → grava `st.session_state["plan_sel_date"]`.
- **Painel de detalhe** (abaixo da grade, para `plan_sel_date`): `profile_chart(mini=False)` grande + `interval_lines` + stats plan/real + botões ⬇ `.zwo` / `.fit` (reusam `GET /plans/workouts/{id}/export.{ext}`).

### Fluxo de dados
1. `GET /plans/{id}/workouts` → planejados (agora com `structure`, `name`).
2. `GET /workouts?start=<início do plano>&end=<race_date>` → realizados.
3. Indexa ambos por data (ISO). Renderiza a semana visível a partir da união de datas.

## Tratamento de erros
- Sem plano → mensagem existente ("gere um plano"). Inalterado.
- Plano sem expandir (lista vazia) → calendário mostra dias vazios + o botão "Gerar treinos diários até a prova".
- Erro de API → `st.error` com status/texto.
- `structure` vazia/malformada → célula sem gráfico, mas com tipo/TSS (degrada bem).

## Testes
- **`frontend/test_calendar_view.py`** (rodar em `python:3.12-slim` com pytest; sem streamlit/altair pois as funções testadas são puras):
  - `flatten_structure`: expande `Repeat` (conta segmentos e soma durações), ignora estrutura vazia.
  - `zone_of`: limites das 7 zonas.
  - `interval_lines`: formata aquecimento, bloco repetido (`N×`), volta calma.
  - `adherence`: limiares verde/amarelo/vermelho; casos sem plan/sem actual.
- **Backend:** atualizar `test_list_plan_workouts` para exigir `structure` (e `name`) no retorno.
- **Sintaxe:** `ast.parse` de `frontend/app.py` e `frontend/calendar_view.py` no container slim.
- **Verificação ao vivo:** `docker compose up -d --build api frontend`; logar; aba 📅 Plano → ver o calendário semanal, navegar semanas, selecionar um dia, baixar .zwo/.fit.

## Comandos (do plano anterior, reaproveitar)
- Backend test: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -v"`
- Frontend pure-fn test: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim sh -c "pip install -q pytest && cd /f && python -m pytest test_calendar_view.py -v"`
- Frontend sintaxe: `docker run --rm -i -v "$(pwd -W)/frontend":/f python:3.12-slim python -c "import ast; ast.parse(open('/f/app.py',encoding='utf-8').read()); ast.parse(open('/f/calendar_view.py',encoding='utf-8').read()); print('ok')"`

## Fora de escopo (v2)
- Curva de potência real por-segundo (streams) sobreposta ao planejado.
- Vista mensal / mini-mapa do plano inteiro.
- Arrastar-e-soltar treinos no calendário; edição de treinos.

## Contexto para retomar (PC vai reiniciar)
- Estado atual do branch `feat/daily-plan-expansion`: Tasks 1–5 da expansão diária **concluídas e commitadas** (até `bfaee54`). Suíte backend: 344 passed.
- Senha de teste do `leandro@athletehub.example.com` foi redefinida para **`leandro12345`** (dev local).
- Docker Desktop precisa estar rodando; imagem `aath-backend:latest` existe; `docker compose up -d --build api frontend` sobe API (:8000) e frontend (:8501). Migração 0007 aplica no startup da API.
- **Próximo passo:** invocar `superpowers:writing-plans` para gerar o plano de implementação desta feature.
