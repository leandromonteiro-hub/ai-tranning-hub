# Port do frontend Streamlit → Next.js (com melhorias de UX) — Design

**Data:** 2026-06-24
**Status:** aprovado (aguardando revisão do spec)

## Objetivo

Portar todo o app do atleta/treinador hoje em Streamlit (`frontend/app.py`) para o
painel Next.js criado em `web/`, com **paridade funcional + melhorias de UX**
(navegação por páginas, overview real, gráficos melhores, onboarding guiado).
A migração é **faseada**: o Streamlit (`:8501`) continua no ar e em uso pela
validação dos 2 atletas até o Next atingir paridade (marco M6).

## Contexto

- Backend: FastAPI em `:8000` (`/api/v1`), auth JWT (OAuth2 password), papéis
  `ATHLETE`/`ADMIN`. ~18 endpoints já consumidos pelo Streamlit.
- `web/` já tem: shell autenticado (sidebar + drawer mobile), dark mode por classe,
  tokens genéricos, componentes `ui/{Card,Button,Input,Badge}`, login mockup,
  dashboard de exemplo. **Nada disso fala com o backend ainda.**
- Streamlit consome: `/auth/login`, `/athletes/me`, `/athletes/me/profile`,
  `/metrics/load`, `/metrics/load/recompute`, `/metrics/recovery`,
  `/metrics/subjective`, `/imports/upload`, `/races`, `/plans`, `/plans/generate`,
  `/recommendations`, `/recommendations/{id}/export.{zwo,fit}`,
  `/recommendations/sample.{zwo,fit}`, `/feedback/{id}`, `/admin/usage`,
  `/admin/athletes`, `/admin/feedback`.

## Decisões (do brainstorming)

1. **Auth/dados:** BFF — o navegador fala só com o Next; Route Handlers repassam
   ao FastAPI; JWT em **cookie httpOnly**. Sem CORS, token fora do JS.
2. **Migração:** faseada, Streamlit vivo até paridade (M6).
3. **Fidelidade:** port + melhorias de UX (navegação por páginas, overview novo,
   gráficos recharts, onboarding guiado). Sem novos endpoints nem features de
   produto além das listadas.

## Arquitetura (BFF)

```
navegador ──(/api/*)──> Next.js Route Handlers ──(Authorization: Bearer)──> FastAPI :8000
                              │
                              └── cookie httpOnly "aath_token" (lido server-side)
```

- `app/api/auth/login/route.ts` — POST `{email,password}` → FastAPI `/auth/login`
  (form-urlencoded `username`/`password`); em 200, grava cookie httpOnly
  `aath_token` (Secure em prod, SameSite=Lax, expiração ~ do JWT). Responde
  `{ok:true, role}`.
- `app/api/auth/logout/route.ts` — apaga o cookie.
- `app/api/proxy/[...path]/route.ts` — handler único (GET/POST/PUT/DELETE) que:
  - lê `aath_token` do cookie; sem token → 401;
  - reconstrói a URL `${API}/${path}${search}` e repassa método, query, headers
    relevantes e body (inclui `multipart/form-data` para upload);
  - anexa `Authorization: Bearer <token>`;
  - repassa a resposta **incluindo binários** (.zwo/.fit) com `Content-Type` e
    `Content-Disposition` originais;
  - 401 do backend → propaga 401 (cliente trata limpando sessão).
- `middleware.ts` — nas rotas do grupo `(app)`: sem cookie `aath_token` →
  redireciona para `/login`. (Proteção de presença; a validade real é checada
  pelo backend a cada chamada.)
- `lib/session.ts` (server) — decodifica o payload do JWT (sem verificar
  assinatura; só para ler `role`/`sub` e gatear UI) para Server Components que
  precisam saber o papel (nav admin, redirect de `/admin`).
- `lib/api.ts` (client) — `apiFetch(path, opts)` chama sempre `/api/proxy/${path}`;
  em 401 dispara logout + redirect. GETs via **SWR** (`useApi(path)`); mutações
  via `apiFetch` direto.

## Páginas (rotas)

Todas em pt-BR (consistente com o app atual). Grupo `(app)` = shell autenticado.

| Rota | Origem | Endpoints | Notas |
|------|--------|-----------|-------|
| `(app)/` (overview) | ✨ novo | profile, metrics/load, races, plans | cards de status; só leitura |
| `(app)/anamnese` | 🩺 Anamnese | GET/PUT `/athletes/me/profile` | form completo (15 campos) |
| `(app)/forma-carga` | 📈 Forma & Carga | `/metrics/load`(+`/recompute`) | gráfico recharts CTL/ATL/TSB |
| `(app)/checkin` | 📝 Check-in | `/metrics/recovery` + `/metrics/subjective` | 2 POSTs (data de hoje) |
| `(app)/importar` | 📥 Importar | `/imports/upload` | multipart; tabela do resultado |
| `(app)/provas` | 🏁 Provas | GET/POST `/races` | form + tabela |
| `(app)/plano` | 📅 Plano | `/plans`, `/plans/generate` | barras de TSS + semanas + blocos |
| `(app)/recomendacoes` | 🧠 Recomendações + 🧪 Treinos de teste | `/recommendations`, `/recommendations/{id}/export.{ext}`, `/feedback/{id}`, `/recommendations/sample.{ext}` | gerar IA, exportar, feedback; card de samples |
| `(app)/admin` | 📋 Painel treinador | `/admin/usage`, `/admin/athletes`, `/admin/feedback` | **só ADMIN**; redirect se atleta |

Roteamento por papel: ADMIN ao logar cai em `/admin`; ATLETA em `/` (overview).
A sidebar mostra a seção "Admin" só para ADMIN.

## Melhorias de UX (escopo fechado)

- **Overview real** (`(app)/`): status da anamnese (completa/incompleta + CTA),
  CTL/ATL/TSB atuais, próxima prova + fase de hoje, atalho "Gerar recomendação".
- **Onboarding guiado:** anamnese incompleta → card de chamada no overview e
  `/recomendacoes` exibe aviso + link em vez do formulário (espelha o gate 409 do
  backend).
- **Gráficos:** recharts — área/linhas para CTL/ATL/TSB; barras para TSS planejado.
  Estados de loading e vazio explícitos.
- **Feedback de UI:** toasts de sucesso/erro, validação inline nos forms, dark mode.

Fora de escopo (YAGNI): novos endpoints, edição/remoção de provas/planos que o
Streamlit não tem, i18n, gestão multi-tenant na UI, E2E pesado.

## Componentes

Reuso: `ui/{Card,Button,Input,Badge}`. Novos componentes reutilizáveis:
`ui/Select`, `ui/Textarea`, `ui/Slider`, `ui/Table`, `ui/Stat` (card de KPI),
`ui/Toast` (+ provider), `ui/Spinner`/skeleton. Gráficos em
`components/charts/{LoadChart,TssChart}.tsx` (recharts).

## Fluxo de dados e erros

- GET: `useApi(path)` (SWR) → `/api/proxy/...`. Loading → spinner/skeleton; erro →
  mensagem; vazio → estado vazio.
- Mutação: `apiFetch` POST/PUT → toast de sucesso/erro; revalida SWR relacionado.
- 401 em qualquer chamada → `apiFetch` chama `/api/auth/logout` e manda para `/login`.
- 409 na geração de recomendação (anamnese incompleta) → mensagem específica +
  link para `/anamnese`.
- Upload: `FormData` repassado como `multipart/form-data` pelo proxy.
- Download: link/click busca `/api/proxy/recommendations/.../export.zwo` e força
  download via `Content-Disposition` (o proxy preserva o header do backend).

## Testes (proporcional ao repo)

- **Vitest + React Testing Library** para lógica crítica/pura:
  `anamnese_complete`, formatações (datas, labels de prova/fase), montagem de URL
  do proxy, mapeamento de erro 401/409.
- **Verificação ao vivo por marco** (padrão atual): logar com `athlete1`/`admin`
  e exercitar os fluxos do marco contra API+Postgres reais.
- Sem Playwright/E2E nesta fase.

## Fases (marcos)

Cada marco é independentemente utilizável; o Streamlit permanece como fallback
até M6.

- **M1 — Fundação:** Route Handlers `auth/login`, `auth/logout`, `proxy/[...path]`;
  `middleware.ts`; `lib/{api,session}.ts`; SWR provider; login real (cookie);
  shell/nav refletindo as rotas reais + role-gating; overview esqueleto (sem dados
  ainda). Streamlit intocado.
- **M2 — Atleta core:** `/anamnese`, `/checkin`, `/forma-carga` (recharts),
  `/importar`. Overview passa a mostrar status reais.
- **M3 — Planejamento:** `/provas`, `/plano`.
- **M4 — Loop de IA:** `/recomendacoes` (gerar, exportar .zwo/.fit, feedback) +
  card de treinos de teste.
- **M5 — Admin:** `/admin` (KPIs + atletas + feedbacks), role-gated.
- **M6 — Paridade + aposentar Streamlit:** checklist de paridade 1:1; decisão de
  remover `frontend/` e atualizar `docker-compose` + runbook.

## Riscos / pontos de atenção

- **Compose/infra:** o Next precisará rodar em container (novo serviço `web` no
  `docker-compose`) ou ficar local no dev; definir no M1/M6. A `STREAMLIT_API_BASE_URL`
  vira uma `API_BASE_URL` server-side para o proxy (ex.: `http://api:8000/api/v1`
  dentro do compose).
- **CORS:** não necessário (BFF), mas confirmar que o backend aceita o fluxo de
  login via form-urlencoded a partir do Route Handler (já aceita).
- **Decodificação do JWT** em `lib/session.ts` é só para UI; toda autorização real
  continua no backend.

## Self-review (autor)

- Cobertura: todas as 7 abas + sidebar (treinos de teste) + painel admin mapeadas
  para rotas; todos os ~18 endpoints atribuídos a uma página.
- Sem placeholders/TBD. Sem features novas além das melhorias de UX listadas.
- Consistência: BFF + cookie httpOnly em todas as chamadas; pt-BR nas rotas;
  role-gating coerente entre middleware, `lib/session` e nav.
