# SSO Google + auto-cadastro com convite + portal de onboarding

**Data:** 2026-07-06 · **Status:** aprovado
**Contexto:** piloto vai de 2 para 10 atletas antes do deploy em VPS público.
Hoje o cadastro é admin-gated via API crua (`POST /auth/register`), não há
página de signup, nenhuma lib OAuth existe (backend ou web), e nada guia um
atleta novo pela anamnese. Tudo nesta spec é construção nova.

## Decisões (aprovadas pelo usuário)

- **Provedores:** Google (botão oficial GIS) + email/senha (novo signup
  público). Apple e GitHub adiados. Sem Auth.js, sem IdP gerenciado.
- **Arquitetura SSO:** botão Google no front devolve um **ID token**; o
  backend **verifica a assinatura** (JWKS do Google, lib `google-auth`) e
  emite o JWT próprio do app — uma só fonte de verdade de sessão (o cookie
  `aath_token` de hoje).
- **Gating:** auto-cadastro exige **código de convite** de uso único
  (Anthropic API custa por atleta; LGPD; Garmin não-oficial em escala).
- **Onboarding:** wizard `/bem-vindo` com anamnese **obrigatória** +
  conexão Garmin **opcional** (pulável); bloqueia o resto do app até
  concluir.

## Backend

### Migration 0010

- `athletes.google_sub` — `String(64)`, nullable, **unique** (índice).
- `athletes.hashed_password` — passa a nullable (conta só-Google).
- `athletes.onboarding_completed_at` — `DateTime(timezone=True)`, nullable.
  **Backfill:** atletas existentes recebem `now()` (não caem no wizard).
- Nova tabela `invite_codes`: `id` UUID, `code` String(16) unique (8 chars
  maiúsculos legíveis, sem 0/O/1/I), `created_by` UUID, `used_by_athlete_id`
  UUID nullable, `used_at` nullable, `expires_at` nullable, `created_at`.

### Config

- `google_client_id: str = ""` em `Settings` (+ `GOOGLE_CLIENT_ID` no
  `.env.example`). Vazio ⇒ SSO desligado: `POST /auth/google` responde 503
  e o web não mostra o botão (mesma pattern do `garmin_token_key`).
- Dependência nova no backend: `google-auth` (verificação de ID token).

### Verificador injetável (pattern FakeGarminClient)

`app/services/auth/google_verifier.py`:

- `Protocol GoogleVerifier.verify(credential: str) -> GoogleIdentity` onde
  `GoogleIdentity = {sub, email, email_verified, name}`.
- `RealGoogleVerifier` usa `google.oauth2.id_token.verify_oauth2_token`
  (valida assinatura/JWKS, `aud == settings.google_client_id`, `iss`,
  `exp`). Erro ⇒ `GoogleAuthError`.
- `FakeGoogleVerifier` para testes (identidade configurável / erro).
- Rota usa indireção `_new_verifier()` monkeypatchável (como
  `garmin._new_client`).

### Rotas novas (`app/api/routes/auth.py`)

| Rota | Corpo | Comportamento |
|---|---|---|
| `POST /auth/google` | `{credential, invite_code?}` | Verifica token. (1) `google_sub` existe ⇒ login. (2) email existe e `email_verified` ⇒ **linka** `google_sub` à conta e loga. (3) conta nova ⇒ exige convite válido, cria atleta (role ATHLETE, tenant próprio como hoje, `hashed_password=None`, `full_name` do token), consome convite. Retorna `TokenResponse`. Convite ausente/inválido ⇒ 403 com `detail` distinguindo "convite necessário" de "convite inválido". Token inválido ⇒ 401. Feature off ⇒ 503. |
| `POST /auth/signup` | `{full_name, email, password (min 8), invite_code}` | Público. Convite válido ⇒ cria atleta + consome convite ⇒ `TokenResponse`. Email duplicado ⇒ 409. Convite inválido/usado/expirado ⇒ 403. |
| `POST /auth/me/complete-onboarding` | — | Autenticado; seta `onboarding_completed_at=now()` (idempotente). 204. |
| `GET /auth/me` | — | Ganha campo `onboarding_completed: bool`. |
| `POST /admin/invites` | `{count: int = 1}` (máx 50) | Admin. Gera N códigos; retorna lista. |
| `GET /admin/invites` | — | Admin. Lista códigos com `used_by_email`/`used_at`. |

### Regras

- Convite: uso único, case-insensitive na validação (armazenado maiúsculo),
  `expires_at` respeitado quando presente. Consumo é transacional com a
  criação do atleta (mesmo commit).
- Login por senha (`/auth/login`) numa conta com `hashed_password IS NULL`
  ⇒ 400 `"Esta conta usa Entrar com Google."` (não 401 genérico).
- Linking só quando `email_verified` é true no token; caso contrário 403.
- JWT: passar a incluir claim `email` (hoje `get_current_user` lê
  `payload.get("email","")` que nunca foi gravado — fix).
- `/auth/register` (admin-gated) permanece intocado.

## Web (Next.js)

### BFF routes novas

- `web/app/api/auth/google/route.ts` — recebe `{credential, invite_code?}`,
  repassa ao backend, seta cookie `aath_token` (mesmos flags de hoje),
  devolve `{ok, role}` ou repassa status/detail do erro.
- `web/app/api/auth/signup/route.ts` — idem para signup por senha.

### Páginas

- **`/login`** (`(auth)/login/page.tsx`): + botão oficial GIS "Entrar com
  Google" (script `accounts.google.com/gsi/client` carregado só aqui;
  callback recebe `credential` → POST BFF). Se o backend responder 403
  "convite necessário" (conta Google nova), redireciona para
  `/cadastro?google=1` mantendo o fluxo. + link "Criar conta". Remove o
  email pré-preenchido de dev. Botão só renderiza se
  `NEXT_PUBLIC_GOOGLE_CLIENT_ID` estiver setado.
- **`/cadastro`** (nova, grupo `(auth)`): nome, email, senha, código de
  convite + botão Google (nesse caso só o código é exigido). Erros inline
  (409 email já usado; 403 convite inválido).
- **`/bem-vindo`** (novo, autenticado, FORA do gate): wizard 3 passos com
  indicador de progresso —
  1. **Anamnese** (obrigatória): reusa o form/logic de
     `components/anamnese` (extrair o form para componente reutilizável se
     necessário); avança só depois do PUT com sucesso.
  2. **Garmin** (opcional): renderiza `<GarminCard />` + botão
     "Pular por enquanto".
  3. **Concluir**: `POST auth/me/complete-onboarding` → redirect `/`.
- **Gate de onboarding**: no layout do grupo `(app)`
  (`(app)/layout.tsx`, server-side), consulta `auth/me`; se
  `onboarding_completed === false` e o path não é `/bem-vindo`, redirect
  para `/bem-vindo`. (`/bem-vindo` vive no grupo `(app)` para ter sidebar
  oculta/mínima, mas é isento do gate.)
- **Admin** (`AdminView`): nova seção "Convites" — botão "Gerar convites"
  (POST) + tabela código/status/usado-por, com botão copiar.

### Env

- `NEXT_PUBLIC_GOOGLE_CLIENT_ID` no web (mesmo client id do backend;
  público por natureza). Documentar em `.env.example`.

## Segurança

- ID token verificado criptograficamente no backend; front nunca é
  confiável. `aud`, `iss`, `exp`, assinatura via JWKS Google.
- Rate limit existente (120/min por usuário) cobre; rotas públicas novas
  ficam sob o rate limit por IP existente do app (verificar na implementação
  como o limiter trata anônimo; se não cobrir, aplicar limite simples por IP
  nessas rotas).
- Cookie e flags inalterados (httpOnly, secure em prod, SameSite lax).
- `DEV_AUTO_LOGIN` permanece mecanismo de dev; desligado no deploy.

## Testes

**Backend (pytest, via Docker, TDD):**
- invite: geração (formato/charset), validação case-insensitive, uso único,
  expiração, consumo transacional.
- `/auth/google` com `FakeGoogleVerifier`: login por sub existente; linking
  por email verificado; recusa linking sem email_verified; conta nova sem
  convite ⇒ 403; com convite ⇒ cria e consome; token inválido ⇒ 401;
  feature off ⇒ 503.
- `/auth/signup`: sucesso, email duplicado, convite inválido/usado.
- login por senha em conta só-Google ⇒ 400 com mensagem específica.
- `complete-onboarding` idempotente; `me.onboarding_completed`.
- claim `email` presente no access token.
- admin invites: criação (limite 50), listagem, gates de admin.

**Web (vitest):**
- `/cadastro`: validações, erros 409/403 inline, POST correto.
- botão Google ausente sem `NEXT_PUBLIC_GOOGLE_CLIENT_ID`.
- wizard: passo 1 bloqueia avanço até salvar; passo 2 pulável; concluir
  chama endpoint e redireciona.
- gate: `onboarding_completed=false` redireciona para `/bem-vindo`.

## Fora de escopo

- Apple/GitHub SSO; refresh-token no web (segue M2); recuperação de senha
  por email (piloto: admin reseta); multi-uso de convites; COACH role;
  remoção do fluxo `/auth/register` admin.

## Pré-requisito de infra (manual, você)

Criar OAuth Client ID no Google Cloud Console (tipo "Web application"),
com Authorized JavaScript origins = `http://localhost:3000` e depois o
domínio público do VPS. Sem verificação da tela de consentimento para
escopo básico (email/profile) — modo "testing" com os 10 emails ou
publicado (escopo não-sensível não exige review).
