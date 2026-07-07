# Recomendação comparativa (método tradicional vs. IA)

**Data:** 2026-07-07 · **Status:** aprovado
**Contexto:** hoje a recomendação diária mostra um único treino (estrutura por
`build_for` + texto do LLM). O usuário-treinador quer dar ao atleta
**transparência e liberdade de escolha**: ao lado do treino que a IA recomenda,
mostrar "o que seu método tradicional (o histórico dele / o treinador humano)
faria hoje", para o atleta comparar e escolher. O "método tradicional" já está
modelado no `twin_seed` (engenharia reversa do histórico); falta transformá-lo
num treino concreto.

## Decisões (aprovadas pelo usuário)

- **Dois treinos lado a lado** em cada recomendação diária: **Método tradicional**
  (novo, do `twin_seed`) e **Recomendação da IA** (o atual).
- **A escolha vira o treino do dia**: o atleta clica "Usar este" em um dos dois;
  o escolhido vai ao calendário e é empurrado ao Garmin (reusa o fluxo de
  aceite). A escolha fica registrada como sinal de feedback.
- **Fidelidade do tradicional**: representativo do bloco atual no estilo
  histórico do atleta (distribuição de intensidade + duração/TSS típicos).
- **Zero migração de banco**: o `payload` (jsonb) carrega o segundo treino.

## Arquitetura

### Backend

**1. Novo gerador determinístico `build_methodology_workout(...) -> StructuredWorkout`**
(`app/services/workout/methodology_builder.py`). Contrato:

- Entradas: `intensity_split` (do `twin_seed`: `z1_pct/z2_pct/z3_pct`),
  `block_type`, `ftp_watts`, `typical_duration_s` (duração típica do atleta
  para o contexto — ver §Risco), `risk_level` (respeita o mesmo guardrail:
  HIGH → recuperação).
- Comportamento: escolhe o caráter do treino pela **zona dominante histórica**
  do atleta modulada pelo bloco — atleta pirâmidal/Z2-pesado em BASE → endurance
  Z2 longo; histórico com limiar relevante em BUILD → sweet-spot; pouco Z3 →
  suaviza a intensidade rumo à norma do atleta. Escala a duração para
  `typical_duration_s`. Reusa os primitivos existentes (`Step`/`Repeat`/`Target`
  de `workout/model.py`), `analysis.estimated_tss` e `analysis.describe`.
- Degrada com dados ralos: `data_richness` baixa ou `intensity_split` ausente →
  cai no template genérico do bloco (`build_for`), sinalizando "sem histórico
  suficiente para personalizar".
- **Pura e testável**: nenhuma consulta ao banco dentro do builder; o chamador
  passa `typical_duration_s`.

**2. `recommender.py` (`generate_recommendation`)**: além do `structured_workout`
atual, computa `methodology_workout = build_methodology_workout(...)` e
`methodology_workout_description = analysis.describe(...)`. `typical_duration_s`
é derivado do histórico do atleta (mediana de duração dos treinos concluídos no
bloco/disciplina atuais; fallback por bloco quando ralo). Adiciona ao `payload`:
`methodology_workout`, `methodology_workout_description`. Sem mudança de schema
(`RecommendationRead.payload` é dict verbatim).

**3. Prompt (`prompts.py`, bump de versão)**: injeta o treino tradicional como
contexto para o texto da IA **contrastar explicitamente** — "seu método
tradicional faria X; recomendo Y porque [dados/TSB/tolerância]". Se os dois
coincidirem hoje, a IA declara isso. O `summary`/`rationale` passam a enquadrar
a comparação.

**4. Export do tradicional**: `GET /recommendations/{id}/export.zwo?variant=methodology`
(e `.fit`) lê `payload["methodology_workout"]`; `variant` default = `ai`
(comportamento atual inalterado). Reusa `zwo_encoder`/`fit_encoder`.

**5. Escolha no aceite**: `DecisionRequest` ganha `chosen_variant: "ai" |
"methodology" = "ai"`. Em `POST /recommendations/{id}/decision` com ACCEPTED, o
push ao Garmin usa o treino da variante escolhida; a variante fica registrada
no `AiDecision`/payload (sinal de feedback). O job `push_recommendation_to_garmin`
passa a ler a variante (default `ai` = hoje).

### Frontend (`RecomendacoesView` / `RecsSections` / `recs.ts`)

- Dois cards lado a lado: **"Método tradicional"** e **"Recomendação da IA"**,
  cada um com descrição (`workout_description`), TSS/duração e downloads
  `.zwo`/`.fit` (o tradicional com `?variant=methodology`).
- Botão **"Usar este"** em cada card → dispara o `decision` ACCEPTED com o
  `chosen_variant` correspondente; o outro card marca "não escolhido".
- O texto/rationale da IA por cima explica a diferença.
- `recs.ts`: helpers `methodologyWorkoutDescription(payload)`,
  `hasMethodologyWorkout(payload)` (espelham `workoutDescription`/`hasStructured`).
- Se `methodology_workout` ausente (recomendações antigas / sem histórico) →
  cai no modo de um card só (compatível com o que já existe).

## Risco explícito (a maior incerteza de qualidade)

A **duração/TSS típicos** do treino tradicional não estão prontos no `twin_seed`.
Derivação: mediana da duração dos treinos concluídos do atleta no bloco/
disciplina correntes; fallback por bloco (BASE 90min, BUILD 75min, PEAK 60min,
TAPER 45min, RECOVERY 45min) quando o histórico é ralo. Determinístico e
testável, mas é onde o "tradicional" pode ficar genérico se os dados forem
pobres — nesse caso o builder degrada para o template do bloco e o texto sinaliza
a limitação. Sem histórico → um card só (IA), sem inventar um "tradicional".

## Testes

**Backend (pytest, Docker):**
- `methodology_builder`: pirâmidal/Z2 em BASE → endurance Z2 na duração típica;
  Z3 relevante em BUILD → sweet-spot; HIGH risk → recuperação; `intensity_split`
  ausente/dados ralos → cai no template do bloco; `estimated_tss` coerente.
- `recommender`: payload passa a conter `methodology_workout` +
  `methodology_workout_description`; sem histórico → chave ausente (um card).
- export `?variant=methodology` retorna o .zwo do tradicional; default `ai`
  inalterado.
- decision `chosen_variant="methodology"` → push usa `methodology_workout`;
  default `ai` → comportamento atual.

**Web (vitest):**
- dois cards renderizam quando há `methodology_workout`; um card quando ausente.
- "Usar este" no tradicional chama decision com `chosen_variant="methodology"`;
  no da IA com `"ai"`.
- downloads apontam para a variante certa.

## Fora de escopo

- Aprender/ajustar a metodologia a partir das escolhas (só registramos o sinal
  agora; usar isso é trabalho futuro).
- Mudar como o `twin_seed` é calculado (usa o que já existe; só adiciona a
  derivação de duração típica no recommender).
- Terceira opção / múltiplas variantes — exatamente dois treinos.
- Refactor do `build_for` (permanece a "Recomendação da IA").
