# Regras de Segurança (Safety Guardrails) — Athlete AI Training Hub

> Este documento descreve o **algoritmo de guardrails de segurança** que **DEVE ser executado ANTES de qualquer recomendação da IA**. Nenhuma recomendação é entregue ao atleta sem passar por esta validação. O objetivo é proteger o atleta de sobrecarga, lesão e overtraining, garantindo que toda sugestão respeite os sinais reais de fadiga, recuperação e contexto.

---

## 1. Entradas validadas

O algoritmo recebe e valida obrigatoriamente os seguintes indicadores antes de avaliar qualquer recomendação:

1. **Carga da semana atual** e das **últimas 4 semanas** (TSS semanal / tendência).
2. **CTL atual** e sua **tendência** (taxa de subida — ramp rate).
3. **ATL atual** (fadiga aguda).
4. **TSB atual** (frescor) — *flag* se muito negativo (ex.: entre −20 e −30 ou abaixo).
5. **Sono das últimas 48h** (horas e qualidade).
6. **HRV das últimas 48h** (variabilidade da frequência cardíaca vs baseline).
7. **Fadiga subjetiva** (percepção do atleta, escala).
8. **Histórico de lesões recentes** (lesões/dores ativas ou recém-recuperadas).
9. **Tempo disponível** para treinar (horas reais na semana).
10. **Proximidade de prova-alvo** (dias até a competição; fase: base / específico / taper).
11. **Progressão vs semana anterior** (aumento de carga — máx. ~10%).
12. **Intensidade acumulada nos últimos 7 dias** (tempo/proporção em alta intensidade; monotonia e strain).
13. **Dias consecutivos com carga alta** (sequência sem recuperação adequada).

---

## 2. Classificação de risco

A validação resulta em um de três níveis:

- **RISCO BAIXO** — todos os indicadores dentro de faixas seguras. A recomendação original pode ser entregue normalmente.
- **RISCO MODERADO** — 1 a 2 indicadores em faixa **limítrofe** (warning). A recomendação é entregue **com aviso explícito** e orientação de monitoramento/ajuste.
- **RISCO ALTO** — **qualquer** indicador em faixa **crítica**. A recomendação original é **bloqueada**; o sistema deve sugerir uma **alternativa conservadora** (recuperação, redução de volume/intensidade) e explicar o motivo.

> Regra de prevalência: o nível mais alto disparado prevalece. Um único indicador crítico → RISCO ALTO, independentemente dos demais.

---

## 3. Limiares sugeridos (defaults configuráveis)

> **Todos os valores abaixo são defaults razoáveis e CONFIGURÁVEIS** por atleta/treinador. Devem ser calibrados ao baseline individual. Servem como ponto de partida seguro.

| Indicador | Limítrofe (MODERADO) | Crítico (ALTO) |
|-----------|----------------------|----------------|
| **TSB atual** | −10 a −20 | < −30 |
| **Ramp rate de CTL** (por semana) | 5–7 CTL/sem | > 7–8 CTL/sem |
| **Progressão de carga vs semana anterior** | +10% a +15% | > +15% (acima do teto de 10%) |
| **Monotonia** (carga média / desvio-padrão, 7d) | 1.5 – 2.0 | > 2.0 |
| **Strain** (carga semanal × monotonia) | elevado | muito elevado (sustentado) |
| **Sono (48h)** | 6 – 7 h/noite | < 6 h/noite |
| **HRV vs baseline** | queda 5–10% | queda > 10% (ou supressão sustentada) |
| **Fadiga subjetiva** (escala 1–10) | 7 – 8 | ≥ 9 |
| **Dias consecutivos de carga alta** | 2 dias | ≥ 3 dias |
| **Intensidade acumulada (7d)** | acima do alvo do bloco | muito acima (excesso de alta intensidade) |
| **Histórico de lesão recente** | dor leve / em retorno | lesão ativa / dor que limita |
| **Tempo disponível vs plano** | déficit moderado | déficit que inviabiliza a sessão com segurança |
| **Proximidade de prova** | — | conflito carga alta vs taper/prova iminente |

---

## 4. Pseudocódigo do algoritmo de validação

```python
def validar_seguranca(dados, cfg):
    """
    Executa ANTES de qualquer recomendação da IA.
    Retorna: nível de risco, lista de flags disparadas e se deve bloquear.
    cfg = limiares configuráveis (defaults na seção 3).
    """
    flags = []          # cada flag: (indicador, severidade, detalhe)
    risco = "BAIXO"

    def disparar(indicador, severidade, detalhe):
        flags.append({"indicador": indicador,
                      "severidade": severidade,   # "MODERADO" | "ALTO"
                      "detalhe": detalhe})

    # --- TSB (frescor) ---
    if dados.tsb < cfg.tsb_critico:                       # ex.: < -30
        disparar("TSB", "ALTO", f"TSB={dados.tsb} muito negativo")
    elif dados.tsb < cfg.tsb_limite:                      # ex.: < -20
        disparar("TSB", "MODERADO", f"TSB={dados.tsb} negativo")

    # --- Ramp rate de CTL ---
    if dados.ctl_ramp > cfg.ramp_critico:                 # ex.: > 8/sem
        disparar("CTL_ramp", "ALTO", f"ramp={dados.ctl_ramp}/sem")
    elif dados.ctl_ramp > cfg.ramp_limite:                # ex.: > 5/sem
        disparar("CTL_ramp", "MODERADO", f"ramp={dados.ctl_ramp}/sem")

    # --- Progressão de carga vs semana anterior (teto ~10%) ---
    if dados.delta_carga_pct > cfg.progressao_critico:    # ex.: > 15%
        disparar("Progressao", "ALTO",
                 f"+{dados.delta_carga_pct}% acima do teto de 10%")
    elif dados.delta_carga_pct > cfg.progressao_limite:   # ex.: > 10%
        disparar("Progressao", "MODERADO",
                 f"+{dados.delta_carga_pct}%")

    # --- Monotonia / strain (intensidade acumulada 7d) ---
    if dados.monotonia > cfg.monotonia_critico:           # ex.: > 2.0
        disparar("Monotonia", "ALTO", f"monotonia={dados.monotonia}")
    elif dados.monotonia > cfg.monotonia_limite:          # ex.: > 1.5
        disparar("Monotonia", "MODERADO", f"monotonia={dados.monotonia}")

    if dados.strain > cfg.strain_critico:
        disparar("Strain", "ALTO", "strain muito elevado sustentado")

    # --- Sono (48h) ---
    if dados.sono_h < cfg.sono_critico:                   # ex.: < 6h
        disparar("Sono", "ALTO", f"sono={dados.sono_h}h")
    elif dados.sono_h < cfg.sono_limite:                  # ex.: < 7h
        disparar("Sono", "MODERADO", f"sono={dados.sono_h}h")

    # --- HRV vs baseline (48h) ---
    queda = (dados.hrv_baseline - dados.hrv_atual) / dados.hrv_baseline * 100
    if queda > cfg.hrv_queda_critico:                     # ex.: > 10%
        disparar("HRV", "ALTO", f"queda HRV {queda:.0f}% vs baseline")
    elif queda > cfg.hrv_queda_limite:                    # ex.: > 5%
        disparar("HRV", "MODERADO", f"queda HRV {queda:.0f}%")

    # --- Fadiga subjetiva ---
    if dados.fadiga >= cfg.fadiga_critico:                # ex.: >= 9
        disparar("Fadiga", "ALTO", f"fadiga subjetiva={dados.fadiga}")
    elif dados.fadiga >= cfg.fadiga_limite:               # ex.: >= 7
        disparar("Fadiga", "MODERADO", f"fadiga subjetiva={dados.fadiga}")

    # --- Dias consecutivos de carga alta ---
    if dados.dias_consec_carga_alta >= cfg.dias_consec_critico:   # ex.: >= 3
        disparar("DiasConsecutivos", "ALTO",
                 f"{dados.dias_consec_carga_alta} dias seguidos")
    elif dados.dias_consec_carga_alta >= cfg.dias_consec_limite:  # ex.: 2
        disparar("DiasConsecutivos", "MODERADO",
                 f"{dados.dias_consec_carga_alta} dias seguidos")

    # --- Histórico de lesão recente ---
    if dados.lesao_ativa:
        disparar("Lesao", "ALTO", "lesão/dor ativa que limita treino")
    elif dados.lesao_em_retorno:
        disparar("Lesao", "MODERADO", "retorno recente de lesão")

    # --- Tempo disponível ---
    if dados.tempo_disponivel < dados.tempo_necessario_minimo:
        disparar("Tempo", "MODERADO", "tempo insuficiente p/ sessão planejada")

    # --- Proximidade de prova vs carga ---
    if dados.dias_para_prova <= cfg.janela_taper and dados.carga_alta_planejada:
        disparar("ProvaAlvo", "ALTO",
                 "carga alta conflita com taper/prova iminente")

    # --- Consolidação do nível ---
    if any(f["severidade"] == "ALTO" for f in flags):
        risco = "ALTO"
    elif len(flags) >= 1:
        # 1 a 2 indicadores limítrofes -> MODERADO
        risco = "MODERADO"
    else:
        risco = "BAIXO"

    bloquear = (risco == "ALTO")

    return {
        "risco": risco,            # "BAIXO" | "MODERADO" | "ALTO"
        "flags": flags,            # indicadores disparados
        "bloquear": bloquear,      # True -> bloquear recomendação original
    }
```

**Comportamento por nível:**
- `BAIXO` → entregar recomendação original.
- `MODERADO` → entregar recomendação **com aviso** listando as flags e orientação de ajuste/monitoramento.
- `ALTO` → **bloquear** a recomendação original e entregar **alternativa conservadora** (recuperação ativa, redução de volume e/ou intensidade), explicando as flags críticas.

---

## 5. Campos obrigatórios de toda recomendação

Independentemente do nível de risco, **toda recomendação entregue ao atleta DEVE conter**:

1. **Objetivo fisiológico** — qual adaptação a sessão/ajuste busca (ex.: base aeróbica, VO2max, threshold, recuperação).
2. **Relação com o bloco atual e a prova-alvo** — como a recomendação se encaixa no mesociclo vigente e na preparação para a competição.
3. **Evidência no histórico do atleta** — dados concretos que fundamentam a sugestão (tendência de CTL/TSB, decoupling, sessões anteriores, lacunas na power duration curve).
4. **Nível de confiança (0–1) + justificativa** — quão confiante é a recomendação e por quê (qualidade/quantidade de dados, consistência dos sinais).
5. **Riscos identificados** — flags disparadas pelos guardrails e cuidados associados.
6. **Como ajustar se mais cansado** — instrução clara de regressão (reduzir séries, intensidade, duração ou trocar por recuperação).
7. **Como ajustar se menos tempo** — versão reduzida/priorizada da sessão para tempo disponível menor.

---

## 6. Princípio inegociável

O sistema **nunca substitui avaliação médica ou profissional**. As recomendações são apoio à decisão, baseadas em dados e nas referências conceituais (ver `training_methodology.md`). **O atleta pode sempre rejeitar ou modificar qualquer recomendação.** Em caso de dor persistente, sintomas de saúde ou dúvida, deve-se buscar um profissional qualificado.
