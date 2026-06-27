# Spec — Feedback agregado por tipo de treino

**Data:** 2026-06-27
**Stream:** Training Intelligence Layer · refinamento do feedback loop
**Status:** aprovado (brainstorming), pronto para plano de implementação

## Problema

O feedback loop (shipped 2026-06-27, HEAD `42a53bf`) agrega o feedback do atleta
**por bloco de periodização** (`signals.block`: BASE/BUILD/PEAK/TAPER/RECOVERY).
Bloco é uma fase de treinamento, não o tipo de estímulo do dia. O atleta tende a
reagir ao **tipo de treino** (um VO2máx vs. um longo de endurance), não à fase.
Agregar por tipo torna o contexto de feedback mais preciso e acionável para a IA.

## Objetivo

Trocar o eixo de agregação do feedback de **bloco** para **tipo de treino**
(`WorkoutType`), de forma consistente nos dois fluxos de geração
(`generate_recommendation` e `generate_day_adjustment`), sem migração de banco e
sem mudança de frontend.

Fora de escopo (próximos candidatos, não agora): decay/recência no peso do
feedback; regen de perfil assíncrona; surfacing por tipo no painel do frontend.

## Decisões de design (do brainstorming)

1. **Fonte do tipo no fluxo diário:** derivar deterministicamente de bloco+risco.
   A recomendação diária é montada por bloco (`build_for(block, risk, ftp)`), sem
   enum de tipo. Espelhamos a lógica de seleção de template para derivar o tipo.
2. **Eixo de agregação:** substituir `block` por `workout_type` em todo lugar
   (stats, prompt, tag de comentário). Não manter os dois eixos.
3. **TAPER → OTHER:** o template `openers` (ativação pré-prova) não é um estímulo
   de carga clássico; OTHER é a classificação mais honesta.
4. **Frontend:** sem mudança agora. A linha "Considerou suas últimas N avaliações"
   (`intelligence_view.feedback_line`) já não lê o eixo por-bloco; `by_workout_type`
   vive nos stats (transparência via payload) e no prompt.
5. **Sem migração:** segue o padrão atual — o eixo é lido de `payload.signals`
   (jsonb), não de uma coluna em `ai_recommendations`.

## Componentes

### 1. Derivação do tipo (treino diário) — `services/workout/`

**`templates.py`** — adicionar, ao lado de `TEMPLATES`, um mapeamento paralelo:

```python
BLOCK_WORKOUT_TYPE: dict[BlockType, WorkoutType] = {
    BlockType.BASE: WorkoutType.ENDURANCE,
    BlockType.BUILD: WorkoutType.SWEET_SPOT,
    BlockType.PEAK: WorkoutType.VO2MAX,
    BlockType.TAPER: WorkoutType.OTHER,      # openers (ativação)
    BlockType.RECOVERY: WorkoutType.RECOVERY,
}
```

**`builder.py`** — adicionar `workout_type_for`, que **espelha** `build_for`:

```python
def workout_type_for(block_type: BlockType, risk_level: RiskLevel) -> WorkoutType:
    if risk_level == RiskLevel.HIGH:
        return WorkoutType.RECOVERY            # mesmo override que build_for
    return BLOCK_WORKOUT_TYPE.get(block_type, WorkoutType.ENDURANCE)
```

Pura, sem I/O. A precedência HIGH→RECOVERY fica junto de `build_for`, que aplica
exatamente o mesmo override ao escolher o template `recovery`.

### 2. Wiring — `services/ai/recommender.py`

Ambos os fluxos passam a gravar `signals["workout_type"]` (valor string do enum):

- **`generate_recommendation` (diária):**
  `signals["workout_type"] = workout_type_for(block, safety.risk_level).value`
- **`generate_day_adjustment` (ajuste-do-dia):** usar o tipo **real** do treino
  planejado, que já está em `payload.planned_snapshot.workout_type`:
  `signals["workout_type"] = planned_snapshot["workout_type"]`.

Racional: no ajuste existe um `WorkoutType` real (do `WorkoutPlanned`); usá-lo é
mais honesto que re-derivar. No diário não existe, então derivamos.

### 3. Agregação — `services/ai/feedback_context.py`

- `FeedbackItem.block` → renomear para `workout_type: str | None`.
- `feedback_summary`: ler `((rec.payload or {}).get("signals") or {}).get("workout_type")`
  em vez de `signals.block`.
- `summarize`: `by_block` → `by_workout_type` no stats; agrupar por `workout_type`;
  linha do prompt `"Por bloco:"` → `"Por tipo:"`; tag de comentário
  `[data · tipo]`. A linha "Por tipo:" continua pulando o balde `"—"`.

**Compatibilidade retroativa:** recs antigas têm só `signals.block`, sem
`signals.workout_type`. Para elas `workout_type` resolve para `None` → caem no
balde `"—"`, contadas no agregado geral mas **fora** da linha "Por tipo:" (não
misturam o eixo de bloco no eixo de tipo). Degradação aceitável para o conjunto
de validação de 2 atletas.

## Fluxo de dados

```
geração (diária)     block + risk ──workout_type_for──▶ signals.workout_type ─┐
geração (ajuste)     planned_snapshot.workout_type ────▶ signals.workout_type ─┤
                                                                                ▼
feedback do atleta ──▶ AiRecommendationFeedback ──join──▶ feedback_summary lê
                                                          signals.workout_type
                                                                ▼
                            summarize → {by_workout_type, ...} + texto "Por tipo:"
                                                ▼
                     prompt {feedback}  +  payload.signals.feedback (transparência)
```

## Tratamento de erros / degradação

- Sem feedback na janela (90d): `("n/d", {})` — comportamento atual, inalterado.
- Rec sem `workout_type` nos signals (antiga): balde `"—"`, fora da linha "Por tipo:".
- `workout_type_for` com bloco desconhecido: cai em `ENDURANCE` (default seguro,
  mesma postura de `TEMPLATES.get(..., endurance)`).
- Nota: o fluxo diário só emite 5 dos 10 WorkoutType (ENDURANCE, SWEET_SPOT, VO2MAX, OTHER, RECOVERY, derivados do bloco+risco), enquanto o ajuste-do-dia emite o tipo real do planejado (enum completo). Buckets diários esparsos são esperados — não é erro de wiring.

## Testes

- **Novo unit** `test_workout/test_builder.py` (ou test dedicado): `workout_type_for`
  — cada bloco→tipo esperado **e** o override HIGH→RECOVERY ganhando do bloco.
- **`test_ai/test_feedback_context.py`:** atualizar asserts de `block`→`workout_type`
  e `by_block`→`by_workout_type`; cobrir a linha "Por tipo:" e o balde "—" para
  itens sem tipo.
- **`test_ai/test_signals.py` / `test_ai/test_feedback_wiring.py`:** asserir que
  `signals["workout_type"]` é gravado no fluxo diário.
- **`test_api/test_day_adjustment.py`:** asserir que `signals["workout_type"]`
  reflete o tipo **real** do planejado no fluxo de ajuste.

## Critérios de aceite

1. `signals.workout_type` presente nos dois fluxos, com o valor correto
   (derivado no diário; real no ajuste).
2. `feedback_summary` agrega por tipo de treino; stats expõem `by_workout_type`;
   prompt mostra "Por tipo:".
3. Recs antigas não quebram a agregação (balde "—", fora da linha por tipo).
4. Sem migração; sem mudança de frontend; `feedback_line` segue funcionando.
5. Backend pytest exit 0; frontend verde.
