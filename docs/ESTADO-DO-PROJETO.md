# Estado do projeto — handoff

> Documento de continuidade. Atualizado em **2026-07-30**. Serve para retomar o
> projeto em qualquer máquina (o código e este resumo sincronizam via git).
> **Nenhum segredo aqui** — este repositório é público. Segredos vivem só no
> servidor (`/opt/aath/.env`) e localmente (`.env`, chave SSH), nunca no git.

## Retomar daqui (o que fazer primeiro)

1. **Bloqueado em você:** criar o app da Whoop em `developer.whoop.com`, com
   Redirect URI `https://62-171-128-103.sslip.io/api/whoop/callback`, e pôr
   `WHOOP_CLIENT_ID` / `WHOOP_CLIENT_SECRET` em `/opt/aath/.env`. O código está
   em produção e inerte até isso (ver "Integrações" abaixo).
2. **PR #23 aberto** — `fix/migracoes-do-zero`: revisar e mergear.
3. **Dogfooding:** testar o fluxo na sua própria conta antes de convidar
   qualquer atleta (ver "Piloto" abaixo).

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
- **Nenhum atleta convidado ainda.** O piloto está parado na fase de dogfooding
  (validar usabilidade na conta do próprio Leandro antes de chamar gente).

## Arquitetura

- **backend/** — FastAPI (async), Postgres + pgvector, Redis, Celery
  (worker + beat). **Não há Python no host** — tudo roda em container (ver
  "Testes").
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

## Integrações — estado real

| Provedor | Estado | Observação |
|---|---|---|
| **Garmin** | Em produção, validado com conta real | Lib não-oficial. **Bloqueio de IP de datacenter** (ver abaixo) |
| **Whoop** | Código em produção, **inerte** | Falta criar o app em `developer.whoop.com` e pôr as credenciais no `.env`. App sem aprovação da Whoop atende no máximo 10 membros — suficiente para o piloto |
| **Wahoo** | Não iniciado | API oficial, mas *partner-gated* (`partnerships@wahoofitness.com`) |
| **TrainingPeaks** | Export manual (.zwo) | API oficial é gated. Import manual de HRV/sono foi **descartado** por não ser funcional |

**Whoop — o que já existe:** OAuth2 (state assinado por HMAC, TTL 10 min), token
criptografado com Fernet, job diário + botão manual, backfill de 180 dias,
recuperação e sono. Precedência de fonte: **Whoop vence Garmin** onde as duas
medem a mesma coisa; ausência de medida nunca sobrescreve medida
(`app/services/recovery/merge.py`).

**Garmin — risco em aberto, sem solução:** a Garmin devolve **429 no IP do
VPS** (IP de datacenter). A biblioteca interpretava esse 429 como pedido de MFA
e a UI pedia um código de verificação que **nunca chegava** (não existe 2FA na
conta). O PR #21 corrigiu o *sintoma* — o 429 agora aparece como 429. **A causa
continua de pé**: o sync roda de um IP que a Garmin limita. A resposta de
verdade é arquitetural (proxy residencial ou tirar o sync do datacenter) e
ainda não foi decidida.

## Operação e monitoramento

- **Alerta de job quebrado** (PR #18) — dois checks no healthchecks.io:
  `aath-heartbeat` (15 min, percorre beat→redis→worker→banco) e
  `aath-task-failure`. Runbook completo em `docs/ops/alerta-de-job-quebrado.md`
  — **leia a seção sobre o `aath-task-failure` ser latching antes do primeiro
  incidente**, senão o segundo estouro passa silencioso.
- **Por que isso existe:** em 2026-07-28 o worker ficou **~7 dias quebrado sem
  ninguém notar** (impacto real nulo só porque o piloto estava ocioso). Zumbis
  gerados pelo healthcheck esgotaram os PIDs. Corrigido com `init: true` (#17) e
  com um healthcheck barato e honesto (#22).
- **O `docker compose ps` não prova que o worker funciona** — o healthcheck só
  diz que o processo existe. Quem prova é o heartbeat.

## Testes

- **Backend roda na VM da Contabo**, não no Docker local: imagem `aath-test`,
  diretório `/opt/aath-test` — **isolado da produção (`/opt/aath`), nunca rode
  teste lá**. Hoje: 600 testes passando.
- **Web roda no host:** `cd web && npx vitest run` · `npx tsc --noEmit`.
- A suíte do backend usa **SQLite**, então não consegue executar a cadeia de
  migrações (precisa de pgvector). Migração se verifica à mão contra um Postgres
  descartável na VM.

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
- Testes: ver a seção **Testes** acima (backend na VM, web no host).

## Deploy (produção)

- Stack de produção: `docker-compose.prod.yml` (Caddy na frente, Postgres/Redis
  sem porta pública, sem `DEV_AUTO_LOGIN`, worker + beat).
- Fluxo de deploy no servidor: alinhar com a `main` e rebuildar os serviços
  afetados. **Acesso ao servidor é só por chave SSH** (mantida fora do repo).
  Segredos de produção ficam em `/opt/aath/.env` (chmod 600), nunca no git.
- Backup: `pg_dump` diário com retenção de 14 dias.

## Piloto — por que ainda não começou

A decisão foi **fazer dogfooding primeiro**: validar a usabilidade na conta do
próprio Leandro (`leandro.sp@gmail.com`, 471 treinos importados) antes de
convidar atleta nenhum. O que trava:

- Sem os treinos recentes importados, gerar recomendação não faz sentido — ela
  se apoia na carga dos últimos dias.
- O sync do Garmin esbarra no 429 do IP de datacenter (acima).

## Pendências / próximos passos

**Bloqueado em você (Leandro):**

- Criar o app da **Whoop** e pôr as credenciais no `/opt/aath/.env`.
- Testar o **Racional em português** (PR #20) na sua conta e dizer se o texto
  ficou bom.

**Aberto no código:**

- **PR #23** — cadeia de migrações do zero. Revisar e mergear.
- **Garmin / IP de datacenter** — decidir a resposta arquitetural (proxy
  residencial vs tirar o sync do datacenter). É o que mais ameaça o piloto.

**Riscos registrados e não corrigidos** (conscientes, não esquecidos):

- **`recovery_score` guarda coisas diferentes** conforme a fonte: Body Battery
  (Garmin) e Recovery % (Whoop) dividem a mesma coluna. Comparar série histórica
  entre fontes vai enganar.
- **Baseline de HRV desloca** depois do backfill de 180 dias da Whoop.
- **Sem trava de concorrência** entre o backfill e o sync manual da Whoop.
- Dedup de import insere uma linha `DUPLICATE` a cada re-sync (higiene).

**Backlog:**

- Distribuir convites (começar com 2–3) — depois do dogfooding.
- Integração **Wahoo** (partner-gated). A página Conexões já aceita um segundo
  provedor.
- Reavaliar Sonnet vs Opus (custo/qualidade).
- Domínio próprio no lugar do `sslip.io` (muda `SITE_ADDRESS`, Caddy re-emite o
  HTTPS).

## Documentação viva

Cada feature tem spec + plano em `docs/superpowers/specs/` e
`docs/superpowers/plans/` (datados). São a referência detalhada de cada decisão
e implementação.
