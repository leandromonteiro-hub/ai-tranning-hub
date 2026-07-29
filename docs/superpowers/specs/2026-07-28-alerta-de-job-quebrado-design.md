# Alerta de job quebrado — design

**Data:** 2026-07-28
**Motivação:** incidente do worker (PR #17)

## Problema

Em 2026-07-28 o worker do Celery ficou ~7 dias incapaz de executar qualquer task
(`RuntimeError: can't start new thread`, causado por acúmulo de zumbis do
healthcheck — ver PR #17). **Ninguém percebeu.** O incidente só apareceu porque
alguém foi conferir o deploy manualmente.

O impacto real foi nulo porque o piloto estava ocioso: 0 conexões Garmin ativas,
0 atletas novos na janela. Com atletas reais, o mesmo defeito significaria import
de histórico que nunca completa, métricas que não atualizam e recomendações que
não saem — tudo sem mensagem de erro para o atleta e sem sinal para o operador.

Distribuir os convites com essa cegueira é o risco que este trabalho remove.

## Escopo

Detectar e notificar dois modos de falha distintos:

1. **A infra morreu** — beat, redis, worker ou postgres fora, ou o worker vivo
   mas incapaz de executar tasks (o caso de 2026-07-28).
2. **Uma task individual falhou** — a infra está de pé, mas o job de um atleta
   estourou exceção.

**Fora de escopo:** dashboard de observabilidade, métricas de latência,
agregação de logs, alerta por task crítica separada. O piloto tem 10 atletas;
um sinal de vida e um sinal de falha bastam.

## Decisões

| Decisão | Escolha | Por quê |
|---|---|---|
| Canal | Monitor externo (healthchecks.io) | Um alerta que roda dentro do VPS morre junto com o VPS. Free tier cobre 20 checks. Sem SMTP no projeto. |
| Gatilho do sinal de vida | Heartbeat dedicado, 15 min | Detecta em minutos, não em 24h, e independe de haver atleta conectado. O sync diário do Garmin não serve: com 0 atletas conectados ele terminaria sem exercitar quase nada. |
| Falha de task | Alerta imediato via sinal `task_failure` | Cobre o atleta cujo import morre em silêncio. Reusa a mesma infra. |
| Onde o ping vive | Dentro do app | Um cron externo rodando `celery inspect ping` teria dado **verde** durante todo o incidente: o worker respondia ao broker, mas não conseguia executar task. Versionado e testável. |

## Arquitetura

Dois sinais independentes, um por modo de falha.

**Heartbeat:**

```
beat agenda → redis entrega → worker executa → run_async(select 1) → ping
```

Se qualquer elo quebrar, o ping não sai e o healthchecks.io alerta ao vencer a
janela de tolerância.

O caminho exercitado não é decorativo: `run_async` termina em `asyncio.run` →
`shutdown_default_executor` → `thread.start()` (`app/jobs/_run.py:35`), que é a
linha exata onde o incidente estourou. O heartbeat passa pela falha real, não por
uma aproximação dela.

**Falha de task:** handler no sinal `task_failure` faz `POST` no `/fail` de um
segundo check, com nome da task e a exceção no corpo. Alerta imediato.

Cada sinal tem sua própria URL, então o alerta já identifica qual dos dois
problemas é, sem precisar entrar no servidor.

## Componentes

| Arquivo | Papel |
|---|---|
| `app/core/monitoring.py` (novo) | `ping_monitor(url, suffix="", body=None) -> bool`. Único ponto que fala com o mundo externo. |
| `app/core/config.py` | `monitor_heartbeat_url`, `monitor_failure_url` — ambos `str \| None = None`. |
| `app/jobs/health_job.py` (novo) | Task `monitoring_heartbeat`, no padrão dos demais `*_job.py`. |
| `app/jobs/celery_app.py` | Handler do `task_failure` + entrada no `beat_schedule` (900s). |
| `.env.example` | As duas variáveis, documentadas. |

Sem tabela nova e sem dependência nova — `httpx` já está no `pyproject.toml`.

## Tratamento de erro

Regra que governa o módulo: **um monitor nunca pode derrubar o job que ele
monitora.**

- `ping_monitor()` engole toda exceção e loga `warning`. Rede fora, DNS ruim ou
  healthchecks.io indisponível não afetam o job.
- Timeout de 5s, para não segurar o worker esperando serviço externo.
- URL não configurada → no-op silencioso. Dev e teste não tentam rede, e o
  código pode ir para produção antes de a conta existir.
- O handler do `task_failure` é blindado igual: exceção dentro dele mascararia o
  erro original da task, que é justamente o que se quer enxergar.

Efeito colateral mantido de propósito: se a própria task de heartbeat falhar,
chegam dois alertas (o `/fail` imediato e depois a janela vencida). É redundância
útil, não ruído.

## Testes

TDD, com `httpx.MockTransport` — sem rede real. Docstrings explicando a
regressão, no estilo de `app/tests/test_jobs/test_run_async.py`.

`test_monitoring.py`:
- não faz request quando a URL não está configurada
- faz `POST` na URL certa
- concatena `/fail` corretamente
- erro de rede não propaga
- timeout não propaga

`test_health_job.py`:
- o heartbeat pinga quando o DB responde
- o heartbeat **não** pinga quando o DB falha, e deixa a exceção subir para o
  `task_failure` agir

Handler do `task_failure`:
- chama o ping com o nome da task e a exceção no corpo

## Deploy

Código mudou, então rebuild da imagem do backend e recriar `worker` **e** `beat`
— o beat precisa reiniciar para carregar o novo `beat_schedule`. O `api` roda a
mesma imagem, mas não usa nada deste trabalho; recriar é opcional e só serve
para manter os três na mesma build.

Configuração no healthchecks.io (do lado do operador):

- `aath-heartbeat` — period 15 min, grace 20 min
- `aath-task-failure` — period bem longo; senão o check alerta por silêncio, e
  silêncio é o estado bom

As duas URLs entram em `/opt/aath/.env` (chmod 600), nunca no git.

## Verificação

Com evidência, não com fé:

1. Disparar o heartbeat manualmente e ver o check virar verde no healthchecks.io
2. Forçar uma task a falhar e confirmar que o alerta chega
3. Confirmar que, sem URL configurada, nada quebra
