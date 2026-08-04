# Expansão diária variada do plano — Design

**Data:** 2026-08-03 · **Status:** aprovado no brainstorm (Leandro)

## Problema

A expansão do plano em treinos diários (`plan_expander.py`) produz semanas
monótonas e irreais:

1. **Biblioteca pobre**: 5 templates; na fase BASE todos os dias não-qualidade
   recebem o MESMO "Endurance Z2".
2. **Saturação do teto de escala**: o Z2 escala no máximo 2,5× a duração base
   (`_scaled_endurance`). Para CTL alto (ex.: 119 → alvo ~150 TSS/dia), todo
   dia satura em 170 min / TSS 116 — semanas idênticas entre si e a rampa de
   +8%/semana da periodização some na prática (entrega ~654 de ~830 TSS).
3. **Semana sem forma**: papéis por índice de "dia de treino", sem longão de
   fim de semana nem teto de duração nos dias úteis — 170 min numa quarta-feira
   é irreal para quem trabalha.
4. **Lateral**: dois planos ativos (provas diferentes) prescrevem treino nos
   mesmos dias, sem regra de conflito.

## Decisões (com o atleta)

- Disponibilidade: dias úteis 60-90 min; **longão no domingo** (3-5h).
- Motor **determinístico** (regras + biblioteca), sem LLM. A IA continua
  atuando por cima, na recomendação/ajuste diário.
- Conflito multi-plano: regra simples nesta feature — **prova mais próxima
  vence o dia**. Planos aninhados ficam para depois.

## Design

### 1. Biblioteca de templates (`app/services/workout/templates.py`)

Novos (todos determinísticos, FTP-parametrizados, exportáveis como os atuais):

| Função | Nome | Estímulo |
|---|---|---|
| `long_ride(ftp, duration_s)` | Longão Z2 | Z2 0,62-0,68; duração parametrizada (única com parâmetro extra) |
| `long_ride_tempo(ftp, duration_s)` | Longão com tempo | Z2 com 3 blocos de 15 min Z3 (0,78-0,84) |
| `tempo(ftp)` | Tempo 2x20 | Z3 0,76-0,85 |
| `forca_cadencia(ftp)` | Força 4x8 | 0,75-0,85 FTP, cadência 50-60 rpm (na descrição) |
| `z2_sprints(ftp)` | Z2 + 6 sprints | Z2 com 6×10s neuromuscular (>1,5 FTP, alvo aberto no topo) |
| `z2_progressivo(ftp)` | Z2 progressivo | 3 blocos Z2 subindo até 0,70-0,75 |

Mantidos: `endurance`, `sweet_spot`, `vo2max`, `recovery`, `openers`.

### 2. Esqueleto semanal por bloco (`plan_expander.py`)

Papéis **ancorados no dia da semana** (semana seg→dom; `week_start` é segunda).
Descanso do perfil: `rest = clamp(7 − weekly_days, 1, 3)`; ordem dos descansos:
**seg, sex, sáb** (1º, 2º, 3º).

| Bloco | ter | qua | qui | sáb* | dom |
|---|---|---|---|---|---|
| BASE | sweet spot | Z2 variado | força/cadência | Z2 curto | **longão Z2** |
| BUILD | VO2 | Z2 variado | tempo | Z2 curto | **longão c/ tempo** |
| PEAK | VO2 | Z2 variado | VO2 | regenerativo | longão Z2 (moderado) |
| TAPER | — | openers | Z2 curto | regenerativo | Z2 curto |
| RECOVERY | regenerativo | Z2 leve | regenerativo | Z2 leve | Z2 curto (sem longão) |

\* sáb vira descanso quando `rest ≥ 3`; sex idem quando `rest ≥ 2` (sex ativo =
regenerativo Z1).

Semana da prova (TAPER com `race_date` na semana): openers 2 dias antes da
prova; dias entre openers e prova = regenerativo; dias de prova continuam
bloqueados (regra existente).

**Variação dos dias "Z2 variado"**: rotação determinística por
`week_index % 3` → `z2_sprints`, `z2_progressivo`, `endurance`. Reproduzível.

### 3. Distribuição do TSS semanal

1. **Longão** reserva **40%** do TSS semanal; duração escalada para atingir
   esse alvo, com limites **2h-5h** (sem o teto de 2,5×; escala pelo bloco Z2).
   No PEAK o fator é 30% (volume cede a intensidade); RECOVERY/TAPER não têm
   longão (dom = Z2 curto de duração fixa).
2. **Qualidade** usa o TSS estimado do template (fixo, como hoje).
3. O restante divide igual entre os demais dias ativos, com **teto de 90 min**
   por dia útil (sáb incluso; "Z2 curto" ≤ 75 min).
4. Excedente que não coube volta para o longão (até 5h). O que ainda sobrar é
   **descartado e reportado**: resposta do expand ganha `tss_dropped` (float,
   0.0 quando nada foi descartado). Nunca prescrever o que não cabe.

### 4. Regra multi-plano (dia disputado)

Na expansão do plano P, para cada dia `d` que já tem `WorkoutPlanned` de outro
plano ativo Q (`source_plan_id != P`, plano não deletado):

- `race_date(Q) < race_date(P)` → Q vence; P **não grava** em `d`.
- senão → P vence; a linha de Q em `d` é apagada e P grava.

Sem mudança de schema. O delete idempotente atual (apaga só as linhas do
próprio plano) continua; a regra acima roda na gravação dia a dia.

### 5. O que NÃO muda

- API (`POST /plans/{id}/expand`) e UI — só o corpo da resposta ganha
  `tss_dropped`.
- Periodização semanal (`periodization.py`) — intocada.
- Bloqueio de dias de prova, descanso vindo do perfil, idempotência do expand.
- Sem migração de banco.

## Erros e casos-limite

- Perfil sem `weekly_days` → `rest = 1` (como hoje).
- Semana parcial (começa hoje no meio da semana) → papéis pelos dias restantes
  do calendário (dia da semana continua mandando; sem realocar qualidade).
- FTP ausente → fallback 200 W (como hoje).
- Semana com TSS baixo (deload/taper): dias ativos podem ficar abaixo do teto —
  nunca esticar para "gastar" TSS; o descarte só existe para excesso.

## Testes

- `allocate_days` (puro): longão no domingo com 40%±tolerância; teto de 90 min
  nos dias úteis; rotação de variantes entre semanas; rampa semanal preservada
  (TSS entregue cresce com o planejado até os tetos); deload sem longão;
  semana da prova com openers 2 dias antes; ordem dos descansos seg/sex/sáb.
- Templates novos: TSS estimado em faixas sanas; estrutura serializável.
- Integração multi-plano: P e Q com provas em datas diferentes disputando o
  mesmo dia (os dois sentidos da regra).
- Atualizar os testes existentes de expand que assumem a semana antiga.

## Rollout

Deploy `up -d --build api` (worker/beat não mudam). Depois, regenerar os dois
planos pelo botão "Gerar plano" (a substituição por prova já existe).

---

## Revisão 2026-08-04 (feedback do atleta após o 1º uso)

Correções na forma da semana, decididas com o Leandro:

1. **Domingo é SEMPRE off** — nenhum esqueleto prescreve treino no domingo.
   (Prova no domingo não é exceção de treino: dias de prova continuam
   bloqueados, sem prescrição, como antes.)
2. **Longão no SÁBADO** (não mais domingo). Mesmos parâmetros: 40% do TSS
   semanal (30% no PEAK), 2h-5h.
3. **Dia flex de meio de semana na QUARTA**: o dia "Z2 variado" (rotação
   `z2_sprints`/`z2_progressivo`/`endurance`) deixa de ter duração fixa e
   passa a absorver o TSS restante da semana, com teto de **3h30** (210 min).
   A escala alonga só os blocos "active" com ≥10 min (sprints de 10s não
   escalam). O excedente que não couber segue indo ao longão e depois para
   `tss_dropped`.
4. **Ordem dos descansos** vira **seg, sex, qua** (dom já é estrutural).

Esqueletos revisados (sem domingo):

| Bloco | ter | qua | qui | sex | sáb |
|---|---|---|---|---|---|
| BASE/BUILD/PEAK | qualidade 1 | **Z2 variado flex ≤3h30** | qualidade 2 | regenerativo* | **longão** |
| TAPER | — | openers | Z2 curto | regenerativo* | Z2 curto |
| RECOVERY | regenerativo | Z2 leve | regenerativo | descanso | Z2 curto |

\* vira descanso quando `rest ≥ 2`; qua vira descanso quando `rest ≥ 3`.
Semana da prova: regra do openers (prova−2) inalterada.

---

## Revisão 2 — 2026-08-04 (volume semanal baixo demais)

Diagnóstico: a periodização pede ~CTL×7 de TSS semanal (~830 com CTL 119),
mas os tetos diários entregavam só ~520-550 (~11,5h) — o resto caía em
`tss_dropped` e a forma **cairia**. Gargalo principal: dias de qualidade de
~1h10 sem volume ao redor. Decisões com o Leandro:

1. **Dias de qualidade (ter/qui) estendem com Z2** após o trabalho principal:
   um bloco Z2 (0,62-0,68) é apenso antes da volta à calma, dimensionado pelo
   TSS que sobrou, até o teto de **3h30** por dia.
2. **Sexta em semana de carga**: se sobra TSS, o regenerativo de 45 min vira
   **Z2 leve de até 2h** (`endurance` escalado). Sem sobra (e no taper),
   continua regenerativo de 45 min.
3. **Deload entrega o alvo** (~60% da semana anterior): os dias de Z2 do
   deload (qua e sáb) escalam até **3h/dia** para atingir o TSS planejado da
   semana, em vez das durações fixas de ~45-75 min.
4. **Teto do longão CONFIRMADO em 5h** — o excedente vai para a semana, não
   para o sábado.

**Ordem de absorção do TSS semanal (semana de carga):** longão 40% (cap 5h) →
quarta flex (cap 3h30) → sexta Z2 leve (cap 2h) → extensões Z2 de ter/qui
(cap 3h30 cada) → longão de novo (até 5h) → `tss_dropped`.

Teto de semana resultante: ~16h / ~780-820 TSS — compatível com manter e
construir CTL ~119.

---

## Revisão 3 — 2026-08-04 ("parece um repeat")

Após a rev. 2, o volume ficou certo mas TODO dia útil saturou em 210 min e os
intervalados nunca mudam ("Sweet Spot 3x12" para sempre). Decisões com o
Leandro (aplicar as 3):

1. **Progressão dos intervalados dentro do bloco** — templates de qualidade
   ganham parâmetro `step` (0-2), avançando a cada semana de carga do mesmo
   bloco e resetando no deload ou na troca de bloco:
   - Sweet Spot: 3x12 → 4x12 → 5x12
   - VO2max: 5x4 → 6x4 → 7x4
   - Tempo: 2x20 → 2x25 → 3x20
   - Força: 4x8 → 5x8 → 6x8 (50-60 rpm)
   O nome do treino reflete o degrau (ex.: "Sweet Spot 4x12").
2. **Ondulação dos dias de qualidade** — só UM dia de qualidade por semana
   recebe a extensão Z2 (o "dia grande", até 3h30); o outro fica só com o
   trabalho principal (~1h10-1h30). O dia grande alterna semana a semana
   (ter ↔ qui). Custo aceito: ~-40-60 TSS/semana vs. a rev. 2.
3. **Variantes de longão na BASE** — sábado alterna "Longão Z2" ↔ "Longão com
   giros" (6×3 min a 100-110 rpm dentro do Z2). BUILD segue com "Longão com
   tempo 3x15"; PEAK usa Z2 puro.
