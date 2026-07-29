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

**Verificação pós-deploy:**

1. `docker logs aath_beat` — confirmar que `monitoring-heartbeat` aparece na
   lista de entradas agendadas ao subir.
2. Aguardar até 15 min e conferir no painel do healthchecks.io que o check
   `aath-heartbeat` virou verde (recebeu o primeiro ping). Se não virar, ver
   `aath-heartbeat` vermelho na tabela abaixo.

(A checklist completa de verificação de produção, incluindo o teste do alerta
de falha, vive no plano de implementação em
`docs/superpowers/plans/2026-07-29-alerta-de-job-quebrado.md`.)

## O que cada alerta significa

| Alerta | Significado | Primeiro passo |
|---|---|---|
| `aath-heartbeat` vermelho | beat, redis, worker ou postgres fora — ou o worker vivo sem conseguir executar task (o caso de 2026-07-28) | `docker compose ps` e checar `State.Health`; `docker stats --no-stream --format "{{.Name}}\|{{.PIDs}}"` para ver vazamento de processo |
| `aath-task-failure` disparou | a infra está de pé, uma task individual estourou. O corpo do alerta traz nome da task, id e a exceção | `docker logs aath_worker` filtrando pelo id da task |

### `aath-task-failure` é latching — leia isto antes do primeiro incidente

O healthchecks.io só notifica em **transição** de estado (up→down ou
down→up), não a cada ping. Como nenhum caminho do código manda ping de
sucesso para `MONITOR_FAILURE_URL` — só `/fail` — o check nunca volta a
"up" sozinho. Na prática:

- a **primeira** task que estourar manda `/fail`, o check vai a down, o
  email chega;
- a segunda, a terceira e a centésima task que estourarem depois disso
  mandam `/fail` num check que **já está down** — sem transição, sem email.

Ou seja: se a própria task de heartbeat falhar, chegam **dois** alertas na
**primeira vez** (o `/fail` imediato de `aath-task-failure` e, na sequência,
`aath-heartbeat` vencendo a janela) — mas isso só vale enquanto
`aath-task-failure` ainda está "up". Depois do primeiro incidente de falha
de task, esse segundo alerta fica mudo até alguém fechar o incidente (passo
abaixo). É redundância de propósito, não ruído — mas só na primeira vez.

**Fechamento de incidente (obrigatório depois de resolver uma falha de
task):** resetar `aath-task-failure` para "up", senão o próximo estouro é
silencioso. Duas formas:

- mandar um ping de sucesso na URL **sem** `/fail` (ex.: `curl -fsS -m 5
  https://hc-ping.com/<uuid-do-failure>` a partir do servidor); ou
- no painel do healthchecks.io, Pause e Resume no check.

**Antes de recriar um container em incidente:** `docker logs <container> >
/tmp/incidente.log`. Recriar descarta os logs antigos — foi o que se perdeu no
incidente de 2026-07-28.
