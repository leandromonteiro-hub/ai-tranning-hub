# Alerta de job quebrado — operação

Dois checks no healthchecks.io (free tier). Sem eles configurados o código roda
igual, só não alerta.

## Configurar (uma vez)

1. Criar conta em https://healthchecks.io
2. Criar `aath-heartbeat` — **period 15 min, grace 20 min**
3. Criar `aath-task-failure` — **period bem longo (ex.: 365 dias)**. Aqui o
   silêncio é o estado BOM; com period curto o check alertaria sozinho.
4. Copiar as duas URLs de ping para `/opt/aath/.env` (chmod 600, nunca no git):

   ```
   MONITOR_HEARTBEAT_URL=https://hc-ping.com/<uuid-do-heartbeat>
   MONITOR_FAILURE_URL=https://hc-ping.com/<uuid-do-failure>
   ```

5. Configurar o canal de notificação (email) nos dois checks.

## Deploy

O código mudou, então rebuild da imagem do backend e recriar `worker` **e**
`beat` — o beat precisa reiniciar para carregar o `beat_schedule` novo. O `api`
roda a mesma imagem e não usa nada disto; recriar é opcional, só para manter os
três na mesma build. Os dois containers já leem `env_file: .env`, então não há
mudança de compose.

## O que cada alerta significa

| Alerta | Significado | Primeiro passo |
|---|---|---|
| `aath-heartbeat` vermelho | beat, redis, worker ou postgres fora — ou o worker vivo sem conseguir executar task (o caso de 2026-07-28) | `docker compose ps` e checar `State.Health`; `docker stats --no-stream --format "{{.Name}}\|{{.PIDs}}"` para ver vazamento de processo |
| `aath-task-failure` disparou | a infra está de pé, uma task individual estourou. O corpo do alerta traz nome da task, id e a exceção | `docker logs aath_worker` filtrando pelo id da task |

Se a própria task de heartbeat falhar, chegam **dois** alertas (o `/fail`
imediato e depois a janela vencida). É redundância de propósito, não ruído.

**Antes de recriar um container em incidente:** `docker logs <container> >
/tmp/incidente.log`. Recriar descarta os logs antigos — foi o que se perdeu no
incidente de 2026-07-28.
