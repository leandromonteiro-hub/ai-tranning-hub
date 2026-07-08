# Estado do projeto — handoff

> Documento de continuidade. Atualizado em **2026-07-08**. Serve para retomar o
> projeto em qualquer máquina (o código e este resumo sincronizam via git).
> **Nenhum segredo aqui** — este repositório é público. Segredos vivem só no
> servidor (`/opt/aath/.env`) e localmente (`.env`, chave SSH), nunca no git.

## O que é

Athlete AI Training Hub — sistema de treino de ciclismo assistido por IA, em
validação com um piloto de ~10 atletas antes de comercializar. A IA gera
recomendações de treino personalizadas a partir do histórico real do atleta (um
"digital twin" — engenharia reversa da metodologia dele) + guarda-corpos de
ciência do esporte.

## Estado atual

- **Em produção**, no ar em `https://62-171-128-103.sslip.io` (VPS, Docker
  Compose + Caddy com HTTPS automático). Deploy segue a branch `main`.
- Pronto para o piloto: cadastro por convite, SSO Google, onboarding, dashboard,
  sync Garmin (import + export), recomendação comparativa.

## Arquitetura

- **backend/** — FastAPI (async), Postgres + pgvector, Redis, Celery
  (worker + beat). Testes só via Docker (não há Python no host).
- **web/** — Next.js 15 (App Router) + SWR + Tailwind. Frontend principal.
  Testes no host (`cd web && npx vitest run`; typecheck `npx tsc --noEmit`).
- **frontend/** — Streamlit legado (não recebe features novas).
- **IA** — serviço único no servidor (Anthropic, modelo Opus 4.8). Não há IA por
  atleta; o "próprio de cada atleta" é o `twin_seed` (gerado automático dos dados).
- **Estrutura de treino é determinística** (`build_for` / `methodology_builder`);
  o LLM só escreve o texto (racional, resumo, contraste).

## Funcionalidades entregues (piloto)

- **Auth/onboarding:** SSO Google + email/senha, ambos por **código de convite**
  (uso único, gerado no painel admin); wizard `/bem-vindo`
  (Anamnese obrigatória → Importar histórico → Garmin → Concluir).
- **Sync Garmin** (lib não-oficial `garminconnect`): import diário (atividades +
  wellness) via Celery Beat + on-demand; export do treino aceito para o
  calendário do Garmin. UI na página **Conexões**.
- **Dashboard "Visão geral"**: forma (CTL/ATL/TSB), próximo treino, semana +
  recomendação.
- **Recomendação comparativa**: mostra lado a lado o treino que o "método
  tradicional" do atleta (twin) prescreveria vs o que a IA recomenda; o atleta
  escolhe qual vira o treino do dia (vai pro Garmin).
- **Importar**: upload de arquivos (CSV TrainingPeaks, FIT, TCX, GPX) que
  reconstrói o twin/FTP/curva de potência.

## Decisões de produto importantes

- **Obrigatório para o atleta = só a anamnese** (9 campos: nascimento, sexo,
  peso, altura, FCmáx, disciplina, anos de treino, objetivos, horas/semana). Sem
  eles, a recomendação retorna 422.
- **Histórico de treino não é obrigatório, mas é o que dá qualidade** (constrói o
  twin → faz o comparativo funcionar). **NÃO vem 1 ano via Garmin**: o sync só faz
  backfill de ~60 dias e não reconstrói o twin. O caminho do histórico é o
  **import de arquivos** (guiado no onboarding), não estender o backfill do Garmin
  (risco de rate-limit da Garmin).
- **Método tradicional (comparativo) ignora fadiga do dia de propósito** — só
  risco HIGH força recuperação nos dois lados; a IA é quem ajusta no MODERATE. O
  contraste é a feature.

## Como rodar (dev, local)

- Subir a stack: `docker compose up -d --build` (api :8000, web :3000, streamlit
  :8501; Postgres/Redis). O `.env` local (não versionado) configura segredos e
  `LLM_PROVIDER`.
- Testes backend: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest <path> -q"`.
- Testes web: `cd web && npx vitest run` · typecheck `npx tsc --noEmit`.

## Deploy (produção)

- Stack de produção: `docker-compose.prod.yml` (Caddy na frente, Postgres/Redis
  sem porta pública, sem `DEV_AUTO_LOGIN`, worker + beat).
- Fluxo de deploy no servidor: alinhar com a `main` e rebuildar os serviços
  afetados. **Acesso ao servidor é só por chave SSH** (mantida fora do repo).
  Segredos de produção ficam em `/opt/aath/.env` (chmod 600), nunca no git.
- Backup: `pg_dump` diário com retenção de 14 dias.

## Pendências / próximos passos

- **PR aberto:** `feat/onboarding-prontidao` (valida anamnese + passo de importar
  histórico) — merge + deploy.
- Distribuir convites aos atletas (começar com 2–3).
- Integração **Wahoo**: API oficial (OAuth 2.0, import + push), mas
  **partner-gated** — requer solicitar acesso a `partnerships@wahoofitness.com`.
  A página Conexões já está pronta para receber um segundo provedor.
- Backlog técnico: o dedup de import insere uma linha `DUPLICATE` a cada re-sync
  (higiene — parar de inserir); enxugar o texto do "Racional" da recomendação
  (prompt) e reavaliar Sonnet vs Opus (custo/qualidade).
- Trocar por domínio próprio no lugar do `sslip.io` (muda `SITE_ADDRESS`, Caddy
  re-emite o HTTPS).

## Documentação viva

Cada feature tem spec + plano em `docs/superpowers/specs/` e
`docs/superpowers/plans/` (datados). São a referência detalhada de cada decisão
e implementação.
