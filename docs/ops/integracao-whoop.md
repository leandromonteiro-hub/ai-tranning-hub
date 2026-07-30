# Integração Whoop (HRV, sono, recuperação) — operação

Traz HRV, FC de repouso, score de recuperação, horas e performance de sono da
Whoop para `recovery_metrics` — o dado que faltava na recomendação da IA. API
oficial v2 com OAuth2: sem senha do atleta passando por nós, e sem o bloqueio de
IP de datacenter que trava o Garmin.

## Configurar (uma vez)

1. Criar o app em **https://developer.whoop.com** — imediato, **sem aprovação**,
   com limite de **10 membros Whoop conectados**. Aprovação só é necessária para
   passar dos 10, ou seja, para lançamento comercial.
2. Registrar o **Redirect URI**, exatamente:
   `https://<SEU_DOMINIO>/api/whoop/callback`
   (hoje: `https://62-171-128-103.sslip.io/api/whoop/callback`)
3. Copiar Client ID e Client Secret.
4. Gerar a chave Fernet do token em repouso:
   ```
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
5. Colocar as três em `/opt/aath/.env` (chmod 600, **nunca no git**):
   ```
   WHOOP_CLIENT_ID=...
   WHOOP_CLIENT_SECRET=...
   WHOOP_TOKEN_KEY=...
   ```
   `SITE_ADDRESS` já existe no `.env` e agora também é lido pelo backend, para
   montar o `redirect_uri`. Se ele estiver vazio, as rotas respondem 503.

## Deploy

1. `alembic upgrade head` — cria `whoop_connections` (migração 0011)
2. Rebuild da imagem do backend
3. Recriar `api`, `worker` **e** `beat` — o beat precisa reiniciar para carregar
   a entrada nova do `beat_schedule` (cron às 08:00 UTC)

Sem as variáveis configuradas, as rotas respondem 503 e o card não aparece na
tela de Conexões: o código pode ir para produção antes de o app existir.

## As duas armadilhas

**O Redirect URI é amarrado ao domínio.** Registrado com `sslip.io`, a troca para
domínio próprio **exige reeditar o app no portal da Whoop**. O OAuth quebra de
forma pouco óbvia quando o `redirect_uri` enviado não é idêntico ao registrado —
a Whoop recusa antes de o atleta ver qualquer tela nossa.

**O limite de 10 membros é do app, não da conta do atleta.** O 11º atleta recebe
erro na troca de token, e o card explica isso em português. Se precisar de mais,
é o processo de aprovação da Whoop (exige política de privacidade, testes com ao
menos um membro e conformidade com as diretrizes de marca).

## O que cada estado significa

| Estado | Significado | Primeiro passo |
|---|---|---|
| `CONNECTED` com `last_sync_at` de hoje | Tudo bem | — |
| `CONNECTED` sem `last_sync_at` recente | O beat não rodou, ou o sync falha em silêncio | `docker logs aath_worker` filtrando por `whoop` |
| `NEEDS_REAUTH` | O atleta revogou o acesso no app da Whoop, ou o refresh token expirou | O atleta clica em **Reconectar** na tela de Conexões |
| Alerta de `task_failure` com `whoop_sync` | Falha real na integração | O corpo do email traz o nome da task e a exceção |

A integração já nasce monitorada: qualquer estouro nas tasks `whoop_sync`,
`whoop_backfill` ou `whoop_beat_sync_all` dispara o alerta de job quebrado que
está em produção desde 2026-07-29.

## Precedência com o Garmin

As duas fontes gravam na mesma linha (uma por atleta por dia). A **Whoop vence**
para HRV, sono e recuperação — é pulseira usada 24h, feita para medir sono e HRV
noturno. O Garmin preenche o que a Whoop não trouxe, e **nenhuma fonte sobrescreve
valor existente com vazio**.

A coluna `source` registra quem contribuiu no dia: `whoop`, `garmin` ou
`whoop+garmin`. Para conferir:

```sql
select metric_date, hrv_ms, sleep_hours, source
from recovery_metrics
where source like '%whoop%'
order by metric_date desc limit 10;
```

## Consultas úteis

```sql
-- Estado das conexões
select a.email, w.status, w.last_sync_at, w.backfilled_at, w.last_error
from whoop_connections w join athletes a on a.id = w.athlete_id
where w.deleted_at is null;

-- Quantos membros contam para o limite de 10
select count(*) from whoop_connections
where status = 'CONNECTED' and deleted_at is null;
```
