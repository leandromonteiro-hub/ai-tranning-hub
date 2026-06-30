# Sincronismo bidirecional com Garmin Connect — Design

**Data:** 2026-06-30
**Status:** Aprovado (brainstorming) — aguardando plano de implementação
**Projeto:** Athlete AI Training Hub

---

## 1. Objetivo

Sincronizar dados entre o Garmin Connect do atleta e o Hub, nas duas direções:

- **Import (Garmin → Hub):** atividades executadas (treinos) + wellness (HRV, FC repouso, sono, Body Battery).
- **Export (Hub → Garmin):** treinos estruturados planejados, empurrados e agendados no calendário do Garmin.

Escopo do piloto: **2 atletas** (validação antes de comercial). Prioriza entregar valor sem depender de parceria oficial.

## 2. Decisões de fundo (e por quê)

| Decisão | Escolha | Razão |
|---|---|---|
| **Via de acesso** | Lib não-oficial `python-garminconnect` (sobre `garth`/DI-OAuth) | API oficial do Garmin é partner-gated, não self-service, pode não aceitar novos parceiros — inviável pra piloto. A lib lê atividades+wellness E cria/agenda workouts estruturados (`CyclingWorkout`, `schedule_workout`). |
| **Credenciais** | Onboarding interativo com MFA; persistir **apenas o token cifrado**, nunca a senha | Com MFA, guardar senha não compra re-login automático (qualquer invalidação dispara OTP humano). Token (refresh OAuth1 ~1 ano) renova o access token sozinho, sem senha/MFA. |
| **Disparo** | Celery Beat diário + botão "Sincronizar agora" + push acoplado ao aceite do plano | Reusa a infra Celery existente; a via não-oficial não tem webhook. |
| **Wellness storage** | Reusar `RecoveryMetric` (não criar tabela nova) | Modelo já tem hrv_ms / resting_hr / sleep / recovery_score / source. |
| **Atividades** | Baixar FIT e passar por `ingestion_service.import_file(bytes, source="garmin")` | Reusa dedup (por content-hash e external_id), normalização e cálculo de TSS já existentes. |

### Riscos conhecidos (assumidos)

- **Fragilidade de auth:** `garth`/DI-OAuth é cat-and-mouse com o Garmin. Há issue aberta (#332, 17/03/2026) de 401 no login e #337 de 429 em logins repetidos. O Garmin muda o fluxo e quebra a lib periodicamente. **Mitigação:** isolar o cliente atrás de uma interface fina; detectar 401 e sinalizar reconexão; nunca derrubar o sync de outros atletas.
- **ToS:** uso não-oficial é zona cinzenta. **Mitigação:** consentimento explícito do atleta no onboarding; piloto-only; reavaliar parceria oficial se for comercial.
- **Token é credencial bearer:** vazamento = acesso total. **Mitigação:** cifrar em repouso (Fernet), chave fora do banco (`.env`).

## 3. Arquitetura

A peça frágil (`garminconnect`) fica isolada atrás de uma interface fina (`Protocol`), para que falhas de auth atinjam um só módulo e tudo seja testável com um fake sem rede.

```
backend/app/
  services/garmin/
    client.py          # ÚNICO lugar que importa garminconnect. Wrapper fino.
    token_store.py      # Fernet encrypt/decrypt do token e do client_state MFA
    sync_service.py     # orquestra pull + push, idempotente, injeta o client
  models/garmin.py      # GarminConnection (1 linha/atleta)
  jobs/garmin_job.py     # task Celery sync_athlete_garmin(athlete_id) + Beat diário
  api/routes/garmin.py   # /connect, /connect/mfa, /sync, /status, /disconnect
  schemas/garmin.py      # Pydantic de request/response
```

## 4. Componentes e contratos

### 4.1 `client.py` — wrapper fino (Protocol)

Único módulo que toca `garminconnect`. Interface estável consumida pelo resto:

```python
class GarminClient(Protocol):
    def login(email, password) -> LoginResult
        # LoginResult = Connected(token_dict) | NeedsMfa(client_state)
    def resume_mfa(client_state, mfa_code) -> token_dict
    def resume(token_dict) -> None            # reusa token; refresh OAuth2 automático
    def list_activities(since: date) -> list[ActivityRef]
    def download_activity_fit(activity_id) -> bytes
    def get_wellness(day: date) -> WellnessSnapshot
    def push_workout(structured_workout, schedule_date: date) -> garmin_workout_id
    def unschedule_workout(garmin_workout_id) -> None
```

- `WellnessSnapshot`: hrv_ms, resting_hr, sleep_hours, sleep_score, body_battery (→ recovery_score). Stress fora do MVP (YAGNI).
- Erros de auth da lib são traduzidos para uma exceção própria `GarminAuthError` (o resto do sistema não conhece exceções do `garminconnect`).
- Implementação real: `RealGarminClient`. Testes: `FakeGarminClient` (mesmo Protocol, sem rede).

### 4.2 `token_store.py` — fronteira de cripto

- `encrypt(data: dict) -> str` / `decrypt(s: str) -> dict` via `Fernet(settings.garmin_token_key)`.
- Usado tanto para o `token_dict` quanto para o `client_state` do MFA.
- Se `garmin_token_key` vazio: levanta erro claro → feature desligada (rotas retornam 503).

### 4.3 `sync_service.py` — orquestração idempotente

Recebe o `GarminClient` por injeção.

- **`pull(athlete)`:**
  1. carrega token → `client.resume(token)`.
  2. `list_activities(since = last_sync_at − 2d)`; para cada → `download_activity_fit` → `ingestion_service.import_file(bytes, filename=f"{activity_id}.fit", source="garmin")`. Dedup por `external_id = activity_id` já existe → reprocessar é seguro.
  3. wellness por dia novo desde `last_sync_at − 2d` → `WellnessSnapshot` → **upsert** em `RecoveryMetric` (unique athlete+date garante idempotência), `source="garmin"`.
  4. grava `last_sync_at`; se o token renovou no `resume`, re-cifra e salva.
- **`push(athlete, recommendation)`:**
  1. `structured_workout` canônico (já em `AiRecommendation.payload["structured_workout"]`) → modelo tipado `CyclingWorkout`.
  2. `push_workout` + `schedule_workout(data)` → guarda `garmin_workout_id` no `extra`/payload do `WorkoutPlanned`.
  3. se o treino for revertido/reajustado → `unschedule_workout(garmin_workout_id)` antes de reenviar.
- **Erros:** `GarminAuthError` (401) → marca conexão `needs_reauth` + `last_error`, encerra a task **sem** afetar outros atletas. `429` → deixa a task Celery fazer retry com backoff; não invalida token. Falha de download de uma atividade → warning, segue as demais.

### 4.4 `jobs/garmin_job.py`

- Task `sync_athlete_garmin(athlete_id)` — uma task por atleta (isolamento de falha).
- Celery Beat diário itera atletas com `status=connected` e enfileira uma task por atleta.
- Mesmo padrão dos jobs existentes (`import_job`, `metrics_job`).

### 4.5 `api/routes/garmin.py`

| Método | Rota | Função |
|---|---|---|
| POST | `/garmin/connect` | `{email, senha}` → `login`. Se `NeedsMfa`: cifra `client_state`, grava com TTL ~5min, `status=awaiting_mfa`, retorna `{needs_mfa: true}`. Se `Connected`: grava token, `status=connected`. **Senha nunca persiste.** |
| POST | `/garmin/connect/mfa` | `{code}` → descriptografa `client_state` → `resume_mfa` → cifra token, `status=connected`, limpa `client_state`. |
| POST | `/garmin/sync` | dispara pull on-demand; retorna `task_id` (igual aos outros jobs). |
| GET | `/garmin/status` | status da conexão, `last_sync_at`, flag `needs_reauth`. |
| DELETE | `/garmin/disconnect` | apaga token e zera a conexão. |

- Todas tenant-scoped (atleta A nunca vê/aciona conexão de B).
- Se `garmin_token_key` vazio → 503 em todas.

## 5. Modelo de dados

### Migration `0009_garmin_connection.py`

Tabela `garmin_connections` (TenantMixin):

| coluna | tipo | nota |
|---|---|---|
| `id` / `athlete_id` / `tenant_id` | padrão | `athlete_id` UNIQUE |
| `status` | enum `garmin_connection_status` | `awaiting_mfa` / `connected` / `needs_reauth` / `disconnected` |
| `encrypted_token` | Text, nullable | token garth cifrado (Fernet) |
| `mfa_state` | Text, nullable | `client_state` cifrado; limpo após conectar |
| `mfa_expires_at` | DateTime(tz), nullable | expira o passo 2 do MFA |
| `last_sync_at` | DateTime(tz), nullable | |
| `last_error` | Text, nullable | última mensagem de erro/401 |
| `connected_at` | DateTime(tz), nullable | |

- **Sem tabela nova de wellness:** mapeia em `RecoveryMetric` existente.
- **Sem coluna nova pro `garmin_workout_id`:** vai no `extra`/payload do `WorkoutPlanned` existente.

### Settings (`config.py`)

- `garmin_token_key: str = ""` — chave Fernet (`Fernet.generate_key()`), no `.env`. Vazia ⇒ feature desligada.

### Deps (`pyproject.toml`)

- `+ garminconnect>=0.3.6`
- `+ cryptography>=42` (explicitar; hoje vem transitivo via `python-jose[cryptography]`)

## 6. Estratégia de testes

Tudo offline — `garminconnect` só é tocado em `client.py`, então `FakeGarminClient` cobre o resto.

- **token_store:** round-trip encrypt→decrypt; erro claro com chave vazia.
- **sync pull:** cria atividades pela pipeline real; rodar 2× não duplica (external_id); wellness faz upsert idempotente em `RecoveryMetric`.
- **sync push:** tradução `structured_workout`→`CyclingWorkout` verificada no payload que o fake recebe; reverter chama `unschedule`.
- **erro de auth:** fake levanta `GarminAuthError` → service marca `needs_reauth`, não derruba outros atletas.
- **API:** `/connect`→`/connect/mfa` com fake (passo 1 `needs_mfa`, passo 2 resume+grava); `/status` reflete `needs_reauth`; isolamento por tenant.
- **Não testado automaticamente:** a lib `garminconnect` em si e a auth real do Garmin (rede/credenciais) — verificação manual live no onboarding do piloto.

## 7. Verificação manual (gate do piloto, fora de código)

1. Onboarding real de 1 atleta com MFA → token persiste cifrado.
2. Pull traz atividade real + wellness do dia; rodar de novo não duplica.
3. Push de um treino planejado aparece agendado no calendário do Garmin do atleta.
4. Reverter um treino remove o agendamento.
5. Forçar expiração/401 → `status=needs_reauth` e UI pede reconexão.

## 8. Fora de escopo (YAGNI / fases futuras)

- Stress como métrica persistida.
- Webhook/near-real-time (a via não-oficial não tem).
- API oficial de parceiro (reavaliar se comercial).
- Sync de wellness de outras fontes (Oura/Whoop) — specs próprios.
- Retry automático de re-auth sem intervenção (MFA exige humano).

## 9. Wiring do export (push) — IMPLEMENTADO

**Feito em 2026-06-30** (mesma branch/PR): o export agora está fiado no fluxo de decisão da
recomendação. No `POST /recommendations/{id}/decision`, best-effort (nunca quebra a decisão) e
só com a feature ligada:

- **ACCEPTED** → enfileira o job Celery `garmin_push_recommendation`, que (se a feature está
  ligada, o Garmin está conectado, a rec tem `payload["structured_workout"]` e `target_date`)
  traduz e empurra via `sync_push`, agenda em `target_date`, e guarda o `garmin_workout_id` em
  `rec.payload["garmin_workout_id"]` (reassign do JSONB).
- **REJECTED** com `garmin_workout_id` guardado → enfileira `garmin_unpush_recommendation`, que
  faz resume do token e `sync_unpush` (remove o agendamento) e limpa o id do payload.

Jobs com `client_factory`/`session_factory` injetáveis (testados offline), `autoretry_for=
(GarminSyncError,)` com backoff; `GarminAuthError` → commit + needs_reauth. A direção de import
(atividades + wellness) continua via Celery beat diário + on-demand. Validação manual do piloto
(§7 itens 3-4) cobre o caminho de push/unschedule contra o Garmin real.

**Follow-up menor (não bloqueia):** decisão `MODIFIED` não empurra (YAGNI); testes de paths de
erro dos jobs (no_target_date, needs_reauth) podem ser ampliados.
