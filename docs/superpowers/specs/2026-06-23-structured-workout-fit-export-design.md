# Design — Exportador de treino estruturado `.fit` (fatia fina)

**Data:** 2026-06-23
**Status:** Aprovado (aguardando revisão do spec escrito)
**Fase do projeto:** Fase 0 — validação com 2 atletas
**Contexto relacionado:** `docs/api_integrations.md`, memória `trainingpeaks-export-route`

---

## 1. Motivação

Pesquisa verificada (2026-06-23) mostrou que a API oficial do TrainingPeaks está fechada
(comercial, gated, e atualmente sem aceitar novos parceiros) e que **não existe** um fluxo
aberto de "treino planejado → calendário do TP" via Garmin Connect (o fluxo planejado é
TP→Garmin, não o inverso). O Strava não entrega treino planejado (é diário de atividades
concluídas).

Conclusão estratégica: em vez de depender do TrainingPeaks como calendário, o sistema pode
**gerar o treino estruturado internamente e entregá-lo direto ao ciclocomputador do atleta**.
O "último metro" até o device permanece sendo upload manual de arquivo (mesma barreira que o
TP), mas controlamos calendário e experiência.

Esta fatia fina prova a hipótese-chave antes de qualquer investimento maior:
**"um treino estruturado gerado pelo nosso sistema chega ao ciclocomputador do atleta."**

## 2. Objetivo e fronteira

**Em escopo:** ao gerar uma recomendação diária, o sistema também produz um treino
estruturado determinístico (intervalos com alvos de potência em %FTP) e o atleta baixa um
arquivo `.fit` workout pela UI para importar no device.

**Fora de escopo (YAGNI — fases futuras, reusando o modelo canônico):**
- Calendário dia-a-dia / semana de treinos planejados.
- Persistência do treino estruturado como tabela de 1ª classe.
- Outros formatos de export (`.zwo`, `.erg`, `.mrc`).
- Push automático / API de parceiro (Garmin Training API, Wahoo Cloud).
- Editor manual de treino na UI.
- Alvos por frequência cardíaca (apenas potência %FTP nesta fatia).

## 3. Arquitetura e fluxo de dados

```
recommender.generate_recommendation()
    │  (existente: twin → guardrails → evidência → LLM → persiste)
    └─▶ workout.build_for(block_type, risk_level, ftp_watts)   [NOVO, determinístico]
            └─▶ StructuredWorkout (modelo canônico Pydantic)
                    └─ serializado em AiRecommendation.payload["structured_workout"]

GET /api/v1/recommendations/{id}/export.fit   [NOVO endpoint]
    └─▶ lê payload → fit_encoder.encode(workout, ftp_watts) → bytes .fit
            └─▶ download (Content-Disposition: attachment; filename=<slug>.fit)

Streamlit: botão "⬇️ Baixar treino (.fit)" na aba Recomendações  [NOVO]
```

**Decisões:**
- Nenhuma tabela nova, nenhuma migração (reusa `AiRecommendation.payload`, JSONB já existente
  e comentado `# structured workout`).
- FTP atual obtido de `FtpHistory` (`ftp_watts`, `valid_to IS NULL` = vigente) via o
  repositório existente.
- Três unidades novas, cada uma com um propósito único e testável isoladamente:
  **builder** (intenção → estrutura), **encoder** (estrutura → bytes `.fit`),
  **endpoint** (entrega).

**Localização do código (novo pacote `app/services/workout/`):**
- `app/services/workout/model.py` — modelo canônico.
- `app/services/workout/templates.py` — biblioteca de templates + seleção.
- `app/services/workout/builder.py` — `build_for(...)` (cola: seleção + escala por FTP).
- `app/services/workout/fit_encoder.py` — encoder `.fit`.

## 4. Modelo canônico (`app/services/workout/model.py`)

Pydantic, agnóstico de formato — a peça reusável nas fases futuras:

```python
class Target(BaseModel):
    type: Literal["power_pct_ftp", "open"]
    low: float | None    # fração do FTP, ex.: 0.88 (88%)
    high: float | None   # ex.: 0.94; watts absolutos resolvidos no encoder

class Step(BaseModel):
    intensity: Literal["warmup", "active", "rest", "cooldown"]
    duration_s: int
    target: Target
    cadence_low: int | None = None
    cadence_high: int | None = None
    note: str | None = None

class Repeat(BaseModel):
    count: int
    steps: list[Step]

class StructuredWorkout(BaseModel):
    name: str
    sport: Literal["cycling"] = "cycling"
    elements: list[Step | Repeat]
    estimated_tss: float | None = None
```

Apenas **potência (%FTP)** nesta fatia. A serialização para `payload` usa
`model_dump(mode="json")`; a leitura no endpoint reconstrói via `StructuredWorkout.model_validate`.

## 5. Biblioteca de templates + seleção (`app/services/workout/templates.py`)

Templates determinísticos parametrizados por FTP, selecionados pela **mesma intenção que os
guardrails já calculam** (`block_type` + `risk_level`). Consequência desejada: o treino
estruturado **respeita os guardrails automaticamente** — risco HIGH cai em recuperação,
exatamente como a recomendação em prosa.

| `risk_level` / `block_type` | Template | Exemplo (alvos em %FTP) |
|---|---|---|
| **HIGH** (qualquer bloco) | Recuperação Z1 | 45 min @ 55% |
| **MODERATE** (qualquer bloco) | versão reduzida do template do bloco | menos repetições / menor duração |
| LOW + BASE | Endurance Z2 | 75 min @ 65% |
| LOW + BUILD | Sweet spot / threshold | warm-up 10min + 3×12min @ 90% (5min @ 55% rest) + cool-down 10min |
| LOW + PEAK | VO2max | warm-up 15min + 5×4min @ 115% (4min @ 50% rest) + cool-down 10min |
| LOW + TAPER | Openers | warm-up 15min + 3×1min @ 110% (3min @ 55% rest) + cool-down 10min |
| RECOVERY (deload) | Recuperação Z1 | 45 min @ 55% |

- `select_template(block_type, risk_level) -> TemplateFn` — função pura.
- Cada `TemplateFn(ftp_watts: float) -> StructuredWorkout`.
- MODERATE deriva do template do bloco aplicando um fator de redução (ex.: −1 repetição ou
  −20% de volume), nunca aumentando intensidade.
- Os números exatos de zona/duração são ancorados em `docs/training_methodology.md` e
  `docs/safety_rules.md` na implementação. Caso o `block_type` não tenha template mapeado,
  o default é Endurance Z2 (conservador).

## 6. Encoder `.fit` (`app/services/workout/fit_encoder.py`)

`encode(workout: StructuredWorkout, ftp_watts: float) -> bytes` produz um FIT workout file
válido com as mensagens:
- **File ID** (`type = workout`).
- **Workout** (`wkt_name`, `sport = cycling`, `num_valid_steps`).
- Uma **Workout Step** por `Step`: `duration_type = time` (`duration_value` em ms),
  `target_type = power`, faixa em **watts absolutos** resolvida de `low/high × ftp_watts`
  (`custom_target_power_low/high`), `intensity` mapeado para `warmup/active/rest/cooldown`.
- `Repeat` → step `repeat_until_steps_cmplt` referenciando o índice do primeiro passo do
  bloco e `repeat_value = count`.

**Implementação:** lib Python **`fit-tool`** como **dependência principal** (o encoder roda em
produção: o endpoint serve o `.fit`). O *decoder* usado só nos testes de round-trip pode ficar
em `[dev]` se for uma lib distinta. **Fallback (abordagem B):** se a `fit-tool` não gerar
workout messages que o Garmin aceite, implementar encoder artesanal do subconjunto FIT
(File ID + Workout + Workout Step), eliminando a dependência. A decisão entre lib e artesanal é
tomada cedo, guiada pelo teste de round-trip (§7).

## 7. Testes (TDD)

Rodam na suíte atual (SQLite em container; `pip install -e '.[dev]'` antes de `pytest`).

- **`templates`/`builder`** (`app/tests/test_workout/test_templates.py`):
  - cada `(block_type, risk_level)` retorna o template esperado;
  - `risk_level=HIGH` sempre cai em recuperação Z1, independentemente do bloco;
  - escala de watts correta a partir do FTP (ex.: 90% de 250W = 225W);
  - MODERATE nunca excede a intensidade do template LOW correspondente.
- **`fit_encoder` round-trip** (`app/tests/test_workout/test_fit_encoder.py`):
  - decodifica o `.fit` gerado e confere nº de passos, durações (s), faixas de potência (W)
    e tipos de intensidade. **Este é o teste que valida tecnicamente o arquivo.**
- **API** (`app/tests/test_api/`):
  - `GET /recommendations/{id}/export.fit` → 200 + bytes parseáveis para o dono;
  - 404 para recomendação sem `structured_workout` no payload;
  - **cross-tenant**: atleta2 recebe 404 ao tentar baixar treino do atleta1 (disciplina de
    isolamento do projeto).

## 8. Endpoint + Frontend

- **Endpoint:** `GET /api/v1/recommendations/{id}/export.fit` em `app/api/routes/recommendations.py`.
  - Isolamento multi-tenant via `RecommendationRepository` existente (atleta só acessa o
    próprio recurso).
  - 404 se a recomendação não existir ou não tiver `structured_workout` (ex.: recomendações
    geradas antes desta feature).
  - `Content-Type: application/octet-stream`,
    `Content-Disposition: attachment; filename="<slug-do-nome>.fit"`.
- **Frontend (`frontend/app.py`):** na aba "🧠 Recomendações", após exibir a recomendação,
  um botão **"⬇️ Baixar treino (.fit)"** que busca os bytes do endpoint e os entrega via
  `st.download_button`. Exibido apenas quando há `structured_workout`.

## 9. Critério de aceitação ("pronto")

1. Suíte de testes verde (atuais 42 + novos testes desta feature).
2. Ao gerar uma recomendação, `payload["structured_workout"]` é preenchido e coerente com o
   `risk_level`/`block_type`.
3. O endpoint entrega um `.fit` parseável; isolamento cross-tenant comprovado por teste.
4. **Verificação no device real (gate manual, não-código):** gerar um `.fit` real e confirmar
   que importa e executa em **um dispositivo de um dos 2 atletas** (modelo a confirmar).
   Sem este passo, apenas metade da hipótese está provada.

## 10. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| `.fit` gerado não importa/executa no Garmin | Teste de round-trip + gate manual no device real (§9.4); fallback para encoder artesanal (§6) |
| `fit-tool` não suportar workout messages | Plano B (encoder artesanal); decisão cedo na implementação |
| Dispositivos dos 2 atletas ainda desconhecidos | Modelo canônico agnóstico; `.fit` é o formato mais universal; confirmar hardware antes do gate de §9.4 |
| Recomendações antigas sem `structured_workout` | Endpoint retorna 404 gracioso; sem migração de dados retroativa |

## 11. Questões em aberto (não bloqueiam a fatia fina)

- Qual o modelo exato do ciclocomputador de cada um dos 2 atletas (define o caminho de
  entrega: sideload USB vs import no Garmin Connect)?
- O parser de workout do device aceita o nosso `.fit` sem perda de estrutura (repetições,
  faixas de potência)?
- Próxima fatia: `.zwo` (cobre Wahoo/Zwift/TP) reusando o mesmo modelo canônico.
