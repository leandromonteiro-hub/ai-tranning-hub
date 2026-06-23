# Design — Painel do treinador/admin (monitoramento da validação)

**Data:** 2026-06-23
**Status:** Aprovado
**Fase do projeto:** Fase 0 — validação com 2 atletas
**Camadas:** Frontend (Streamlit) + mudança mínima de backend (1 campo em schema)

---

## 1. Motivação

A Fase 0 exige que o **admin/treinador veja os feedbacks dos 2 atletas** para conduzir a
validação de 4 semanas. O backend já expõe `GET /admin/usage`, `GET /admin/athletes` e
`GET /admin/feedback` (todas protegidas por `require_admin`), mas não há tela — e o
`FeedbackRead` não atribui o feedback a um atleta. Falta o painel que deixa o owner acompanhar
o uso e a qualidade percebida das recomendações.

## 2. Fronteira

**Em escopo:**
- Detecção de papel no frontend: ADMIN → painel de monitoramento; ATHLETE → dashboard atual.
- `admin_dashboard(token)` com 3 seções: métricas da validação, lista de atletas, feed de
  feedbacks atribuídos ao atleta.
- Backend: expor `athlete_id` no `FeedbackRead` (1 linha) para permitir a atribuição.

**Fora de escopo (YAGNI):** drill-down na carga/plano de um atleta específico (exigiria
endpoints admin cross-tenant novos); edição/CRUD de atletas; export; filtros avançados.

## 3. Mudança de backend (mínima)

`backend/app/schemas/ai.py` → `FeedbackRead`: adicionar `athlete_id: uuid.UUID`. O modelo
`AiRecommendationFeedback` já carrega `athlete_id` (via `TenantMixin`), então a serialização
`from_attributes` o preenche automaticamente — nenhuma query/rota muda. O endpoint
`GET /admin/feedback` passa a retornar `athlete_id` em cada item.

Teste (backend): estender `app/tests/test_api/test_app.py` para, no fluxo de feedback existente,
logar como admin (`admin@example.com`), chamar `GET /api/v1/admin/feedback` e afirmar que o item
traz `athlete_id` igual ao do atleta que deu o feedback.

> Nota: o admin de teste do `conftest`/`test_app.py` não existe hoje no fixture do `client`
> (que cria só 2 atletas). O teste novo cria um Athlete com `role=ADMIN` via o mesmo `maker` do
> fixture (ou um fixture local), loga e consulta. Detalhe fica para o plano.

## 4. Componentes do frontend (`frontend/app.py`)

Todas as chamadas usam o helper `api()` + JWT (rotas admin já protegidas por `require_admin`).

### 4.1 Detecção de papel
Em `main()`: após obter o token, buscar `me = api("GET", "/athletes/me", token).json()`. Se
`me.get("role") == "ADMIN"` → `admin_dashboard(token, me)`; senão → `dashboard(token)` (atual).
(O `dashboard` atual já chama `/athletes/me`; para evitar a chamada dupla, `main` passa `me`
adiante, ou cada dashboard busca o seu — o plano escolhe a forma mais limpa.)

### 4.2 `admin_dashboard(token)`
- Sidebar: saudação + botão "Sair" (mesmo padrão do dashboard de atleta).
- **📊 Métricas da validação** — `GET /admin/usage`; `st.metric` (ou colunas) para: atletas,
  treinos, recomendações, nº de feedbacks, **nota média** (1 casa decimal).
- **👥 Atletas** — `GET /admin/athletes`; tabela: nome, email, ativo (✅/—).
- **💬 Feedbacks** — `GET /admin/feedback` (lista ordenada por data desc). Cruzar `athlete_id`
  com a lista de atletas (`{id: full_name}`) para exibir o nome. Tabela: atleta, nota (1–5),
  fez sentido (✅/—), comentário, data. Vazio → `st.info("Nenhum feedback ainda.")`.

## 5. Dados, erros, estados
- Leituras com fallback a `[]`/`{}` quando `status_code != 200` (padrão do projeto).
- Estados vazios tratados em cada seção.
- Sem `st.rerun()` (painel é só leitura).

## 6. Testes e verificação
- **Backend:** 1 teste novo (admin vê `athlete_id` no feedback) somando à suíte (atual 72).
- **Frontend:** sem testes de UI (padrão); `ast.parse` (sintaxe) + **shakedown ao vivo** logando
  como `admin@athletehub.example.com` / `admin_dev_pwd` e conferindo as 3 seções com dados reais
  (já há feedbacks de testes anteriores na base).

## 7. Riscos
| Risco | Mitigação |
|---|---|
| Chamada dupla a `/athletes/me` (main + dashboard) | `main` busca `me` uma vez e passa o papel/objeto adiante |
| Feedback sem atleta correspondente na lista (ex.: soft-deleted) | Fallback do nome para o `athlete_id` curto quando não encontrado |
| Admin logar e ver dashboard de atleta por engano | Detecção explícita por `role == "ADMIN"` antes de renderizar |
