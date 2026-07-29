# Integração Whoop (HRV, sono, recuperação) — design

**Data:** 2026-07-29
**Motivação:** a recomendação diária hoje sai sem HRV, sono ou FC de repouso

## Problema

No teste de ponta a ponta em produção (2026-07-29), a primeira coisa que a IA
escreveu foi que quase todo insumo dinâmico da decisão estava indisponível: sem
HRV, sem sono, sem fadiga subjetiva. O atleta tem 471 treinos importados, mas
nada de recuperação.

A fonte que existia para esse dado era o Garmin, e ela é frágil por construção:
integração não-oficial via login de usuário, que o Garmin bloqueia por IP de
datacenter — no mesmo dia o servidor levou `429` em duas tentativas seguidas e a
conexão ficou inutilizável por horas.

O atleta é assinante Whoop. A Whoop mede exatamente o que falta, 24 horas por
dia, e expõe **API oficial com OAuth2** — sem login de usuário, sem bloqueio de
IP de datacenter.

## Escopo

Trazer **recuperação e sono** da Whoop para `recovery_metrics`: HRV, FC de
repouso, score de recuperação, horas de sono e performance de sono.

**Fora de escopo:** treinos da Whoop (colidiriam com as atividades do Garmin, e
a Whoop não mede potência); strain (exigiria coluna nova e uma decisão de como a
IA usaria duas escalas de carga); webhook (a recomendação é diária, o ganho de
latência não paga as peças a mais).

## Viabilidade (verificada em 2026-07-29)

| Fato | Fonte |
|---|---|
| App criado **na hora, sem aprovação**, limite de **10 membros Whoop** | [App Approval](https://developer.whoop.com/docs/developing/app-approval/) |
| API v2, OAuth2 — auth em `api.prod.whoop.com/oauth/oauth2/auth`, token em `/token` | [OAuth](https://developer.whoop.com/docs/developing/oauth/) |
| Escopos: `read:recovery`, `read:sleep`, `offline` (refresh token) | [API Docs](https://developer.whoop.com/api/) |
| `GET /v2/recovery` e `GET /v2/activity/sleep`, paginados | [API Docs](https://developer.whoop.com/api/) |
| **100 req/min, 10.000 req/dia**, com cabeçalhos de limite restante | [Rate Limiting](https://developer.whoop.com/docs/developing/rate-limiting/) |

O limite de 10 membros cobre o piloto inteiro. Aprovação só é necessária para
lançamento comercial.

## Mapeamento — nenhuma migração de `recovery_metrics`

| Campo Whoop (v2) | Coluna nossa |
|---|---|
| `score.hrv_rmssd_milli` | `hrv_ms` (já em ms) |
| `score.resting_heart_rate` | `resting_hr` |
| `score.recovery_score` | `recovery_score` |
| `score.sleep_performance_percentage` | `sleep_score` |
| `stage_summary` (leve + profundo + REM, excluindo acordado e sem-dado) | `sleep_hours` |
| — | `source` |

### A qual dia pertence cada registro

A Whoop organiza recuperação por **ciclo fisiológico**, não por data de
calendário — `/v2/recovery` devolve `cycle_id` e `sleep_id`, não uma data. Nossa
`recovery_metrics` é indexada por `metric_date`. A regra de conversão:

**`metric_date` = data local do FIM do sono**, usando o `timezone_offset` do
próprio objeto de sono.

Ou seja: dormiu 23h de segunda e acordou 6h de terça ⇒ o registro é de
**terça** — o dia cujo treino aquela recuperação deve informar. Sem essa regra
explícita, um fuso ou uma virada de meia-noite jogaria o HRV da noite no dia
errado, e a recomendação leria a recuperação de ontem como se fosse de hoje.

## Decisões

| Decisão | Escolha | Por quê |
|---|---|---|
| Precedência entre fontes | **Whoop vence** para HRV/sono/recuperação | Pulseira usada 24h, feita para medir sono e HRV noturno; o Garmin depende de dormir com o relógio |
| Gatilho | Job diário às **08:00 UTC (05:00 no Brasil)** via cron no beat + botão "sincronizar agora" | O dado da noite precisa estar pronto antes de o atleta gerar o treino. O botão é para o dogfooding não esperar 24h |
| Janela de cada sync | **Últimos 3 dias**, não só ontem | A Whoop corrige e completa registros depois da primeira publicação; 3 dias recupera essas correções sem custo relevante |
| Validade do `state` do OAuth | **10 minutos** | Tempo de sobra para autorizar no navegador, curto o bastante para não virar credencial reutilizável |
| Backfill inicial | **180 dias** | Em HRV o que importa é o desvio da linha de base; 6 meses dá base estável. ~180 registros contra um teto de 10.000/dia |
| Escopo de dados | Só recuperação e sono | Ver "Fora de escopo" |
| Procedência | Por **linha**, não por campo | 5 colunas de origem não se justificam para 10 atletas; ver "Limitação aceita" |

## Arquitetura

Reusa o molde da conexão Garmin, que já resolveu os problemas difíceis (token
criptografado por atleta, ciclo de vida da conexão, job no beat, card na tela de
importação). A Whoop é **mais simples**: sem senha do usuário passando pelo nosso
lado, sem MFA, sem login não-oficial — só troca de tokens OAuth.

| Arquivo | Papel |
|---|---|
| `app/models/whoop.py` (novo) | `WhoopConnection` — uma linha por atleta: status, token criptografado, `last_sync_at`, `last_error`, `connected_at`. Sem campos de MFA. |
| `app/services/whoop/client.py` (novo) | Único ponto que fala HTTP com a Whoop: troca código por token, refresh, `GET /v2/recovery`, `GET /v2/activity/sleep`. Traduz erros em `WhoopAuthError` / `WhoopSyncError`. |
| `app/services/whoop/sync_service.py` (novo) | Orquestra o pull: pagina, converte para o formato interno, delega a gravação. Recebe o client por injeção (testável offline). |
| `app/services/whoop/token_store.py` (novo) | Fronteira de criptografia, chave `whoop_token_key`. |
| `app/services/recovery/merge.py` (novo) | **Peça central.** Aplica a precedência e nunca sobrescreve valor existente com vazio. Usada pela Whoop **e pelo Garmin**. |
| `app/jobs/whoop_job.py` (novo) | Três tasks, no padrão dos demais `*_job.py`: backfill de 180 dias (disparada uma vez, na conexão), sync de um atleta (janela de 3 dias — usada pelo botão manual) e entrada do beat que enfileira o sync de todos os atletas conectados. |
| `app/api/routes/whoop.py` (novo) | Iniciar OAuth, callback, status, desconectar, sincronizar agora. |
| `app/core/token_crypto.py` (novo) | Lógica Fernet compartilhada. Os dois token stores viram invólucros finos com a própria chave — sem criptografia duplicada. |
| `app/core/config.py` | `whoop_client_id`, `whoop_client_secret`, `whoop_token_key` — vazios ⇒ feature desligada. |
| `app/jobs/celery_app.py` | Entrada de cron do sync diário no `beat_schedule`. |
| `app/services/garmin/sync_service.py` | Passa a gravar via `merge.py` (corrige o bug do vazio). |
| `web/components/importar/WhoopCard.tsx` (novo) | Card ao lado do Garmin: conectar, status, sincronizar agora, desconectar. |

**Não mexer:** a chave `garmin_token_key` e o `.env` de produção. Renomear
variável de ambiente de integração viva é risco sem retorno. A interface pública
do token store do Garmin (`is_enabled`/`encrypt`/`decrypt`) permanece idêntica,
então nenhum chamador é tocado.

## Fluxo OAuth

O callback chega pelo navegador e precisa saber **qual atleta** está conectando.
Duas proteções, ambas necessárias:

1. **`state` assinado** — ao clicar "Conectar", o backend emite um `state` curto,
   assinado, com `athlete_id` e validade de poucos minutos. Defende de CSRF
   (induzir o atleta a vincular a conta Whoop de terceiro à sua) e amarra o
   callback ao atleta certo.
2. **Sessão do navegador** — o `redirect_uri` aponta para uma rota do app web,
   que já tem o cookie de sessão e repassa `code` + `state` ao backend pelo proxy
   autenticado. O backend confere que o atleta da sessão é o mesmo do `state`
   antes de trocar o código por token.

Escopos pedidos: `read:recovery`, `read:sleep`, `offline`. Access token e refresh
token guardados criptografados. Antes de cada sync, renova se vencido; falha de
renovação ⇒ `NEEDS_REAUTH`.

## Precedência (o coração da mudança)

Como a precedência é fixa, a regra dispensa rastrear origem campo por campo:

| Quem grava | Regra |
|---|---|
| **Whoop** | Grava todo campo preenchido. Campo vazio na resposta **nunca** apaga valor existente. |
| **Garmin** | Grava só onde está vazio, e não toca em campo já preenchido em dia que a Whoop também alimentou. |

Os quatro casos:

- Whoop tem HRV, Garmin não → fica o da Whoop
- Garmin tem HRV, Whoop não (pulseira fora) → fica o do Garmin, e a Whoop não apaga
- Ambos têm → Whoop vence
- Nenhum tem → dia sem HRV, e a IA declara a ausência em vez de inventar

`source` passa a registrar quem contribuiu: `whoop`, `garmin` ou
`whoop+garmin`. Cabe nos 64 caracteres da coluna.

**Correção que vem junto:** hoje o sync do Garmin faz
`existing.hrv_ms = snap.hrv_ms` sem checar, gravando `None` por cima de dado bom
(`app/services/garmin/sync_service.py:104-109`). O merge elimina isso — melhoria
válida mesmo nos dias em que a Whoop não participa.

### Limitação aceita

A procedência é **por linha, não por campo**. Num dia em que as duas fontes
contribuíram, se o Garmin depois corrigir um valor que a Whoop não forneceu, o
valor antigo é mantido. O modo de falha é benigno: dado velho, nunca dado errado
de fonte errada. Resolver exigiria cinco colunas de origem — não se justifica
para 10 atletas.

## Tratamento de erro

| Situação | Comportamento |
|---|---|
| Refresh token rejeitado | `NEEDS_REAUTH`, motivo gravado, tela mostra "Reconectar". Sem laço de retentativa. |
| `429` da Whoop | Respeita `X-RateLimit-Reset`. O job diário desiste e tenta no dia seguinte; o botão manual informa quanto esperar. |
| 5xx / rede | Retentativa com backoff, padrão do `garmin_sync` (3 tentativas). |
| Limite de 10 membros atingido | Mensagem específica em português, não erro genérico. |
| App não configurado | Rotas em 503, card não aparece. |
| Falha de um atleta | Uma task por atleta — o erro de um não interrompe os demais. |

**Encaixe com o monitoramento:** se a task da Whoop estourar, o handler do
`task_failure` (em produção desde 2026-07-29) manda email com nome da task e a
exceção. A integração nasce monitorada.

## Testes

Sem rede real, seguindo o padrão do repositório:

- **Client falso** (`fake_client.py`, como o do Garmin) para o fluxo inteiro rodar offline
- **Os quatro casos da precedência**, um teste cada
- **Bug do Garmin travado por teste:** falha se alguém voltar a escrever vazio por cima de valor bom
- **Token store:** ida e volta da criptografia; erro claro quando a chave falta
- **OAuth:** `state` expirado rejeitado; `state` de outro atleta rejeitado
- **Sync:** backfill de 180 dias com paginação; reexecução idempotente

## Deploy

1. Criar o app no portal `developer.whoop.com` (ação do operador) e registrar o
   `redirect_uri`
2. `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET` e `WHOOP_TOKEN_KEY` em
   `/opt/aath/.env` (chmod 600, nunca no git). Gerar a chave Fernet com:
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
3. Migração Alembic da tabela `whoop_connections`
4. Rebuild da imagem do backend; recriar `api`, `worker` e `beat` (o beat precisa
   reiniciar para carregar o `beat_schedule` novo)

**Duas armadilhas para o runbook:**

- O `redirect_uri` é amarrado ao domínio. Registrado hoje com
  `62-171-128-103.sslip.io`, a troca para domínio próprio exige reeditar o app no
  portal da Whoop.
- O limite de 10 membros é do app, não da conta do atleta. O décimo-primeiro
  atleta recebe erro na troca de token.

## Verificação

Com evidência, não com fé:

1. Conectar a Whoop de um atleta real e confirmar `status=CONNECTED`
2. Confirmar no banco que o HRV e o sono da noite entraram com `source='whoop'`
3. Gerar uma recomendação e verificar que a IA passou a usar HRV e sono em vez de
   declarar "n/d"
4. Rodar o sync duas vezes e confirmar que a segunda não altera nada
5. Confirmar que, sem as variáveis configuradas, as rotas respondem 503 e nada quebra
