# Feature (futura) — Tymewear: métricas respiratórias e VO2max de campo

> **Status: design / documentação apenas.** Esta feature **não está implementada**.
> O objetivo aqui é projetar a arquitetura e deixar **pontos de extensão** claros
> no schema e nos serviços, para acomodar o Tymewear quando for priorizado. Nenhuma
> ingestão de Tymewear é construída agora. Materiais de referência acessados em
> 2026-06-24 (tymewear.com: VO2max explained, validation study, training ebook).

## 1. O que o Tymewear fornece (e como complementa potência e FC)

O Tymewear (chest strap VitalPro) mede a **respiração** continuamente durante o
exercício e deriva marcadores fisiológicos individuais:

- **Ventilação minuto (V̇E)** — volume de ar ventilado por minuto (L/min). Stream contínuo.
- **Frequência respiratória (BR)** — respirações por minuto. Stream contínuo.
- **Limiares ventilatórios** detectados a partir das inflexões da V̇E num teste rampa:
  - **VT1 (limiar aeróbio):** ponto de máxima utilização de gordura; início do aumento da ventilação.
  - **VT2 (limiar anaeróbio):** ponto em que lactato/H⁺ deixam de ser reciclados; aumento marcante da BR.
- **VO2max de campo** — estimado pelas inflexões ventilatórias do teste rampa + características do atleta.

**Validação (segundo o fabricante):** contra o carrinho metabólico Cosmed K5
(padrão-ouro), 26 atletas, teste incremental em ciclismo — V̇E com r≈0,973
(r²≈0,947) e BR com erro absoluto médio ≈1,2 br/min. (Citado como dado do
fabricante; tratar como referência externa, não como validação nossa.)

**Por que complementa potência e FC:**
- **Potência** mede o *output mecânico*; **FC** é uma resposta *atrasada e sujeita a deriva*; a **ventilação/limiares ventilatórios** marcam *transições metabólicas individuais* (VT1/VT2) que nem sempre caem nos mesmos %FTP ou %FCmax entre atletas. Ancorar zonas em VT1/VT2 reduz o erro de prescrição por variabilidade individual.
- **Deriva respiratória** (V̇E/BR subindo para a mesma potência ao longo da sessão) é um sinal precoce de fadiga, complementar ao decoupling de FC (já descrito em `training_methodology.md` §6).
- **VO2max de campo** dá uma série temporal de capacidade aeróbia ao longo da temporada, sem teste de laboratório.

## 2. Modelagem no banco (proposta — pontos de extensão)

> Não aplicar agora. Migração futura (ex.: `00NN_tymewear_respiratory`).

### 2.1 Streams por-segundo — estender `workout_streams`
Adicionar colunas de array nullable (mesmo padrão das existentes `power`/`heart_rate`):
- `ventilation: list[float] | None` — V̇E por segundo (L/min).
- `breathing_rate: list[float] | None` — BR por segundo (br/min).

Mantém uma linha por treino; nulo quando o atleta não usou Tymewear. Sem custo para quem não tem o dispositivo.

### 2.2 Nova tabela `respiratory_metrics` (resultado de teste rampa / marcadores)
Uma linha por avaliação (teste rampa) ou por dia, multi-tenant (`TenantMixin`):
- `test_date: date`
- `vt1_power_w / vt1_hr / vt1_ve` — VT1 ancorado em potência, FC e ventilação (os disponíveis).
- `vt2_power_w / vt2_hr / vt2_ve` — VT2 idem.
- `vo2max_field: float | None` — VO2max de campo (mL/kg/min).
- `protocol: str | None` — ex.: "ramp_cycling".
- `source: str` — `"tymewear"`.

### 2.3 Série temporal de VO2max — `vo2max_history`
Análoga a `ftp_history` (já existe): `vo2max_field`, `valid_from`, `valid_to`, `method`, `source`. Permite acompanhar a evolução da capacidade aeróbia ao longo da temporada (re-teste a cada ~4–8 semanas, como recomenda o material do fabricante).

> **Separação de dados:** tudo `source="tymewear"`, isolado por `athlete_id`, como já fazemos com o resto. VT1/VT2/VO2max medidos são **dado real**; zonas derivadas deles são **dado inferido** (manter o rótulo, como na Tarefa 2).

## 3. Como a Training Intelligence Layer usaria

- **Zonas por limiares ventilatórios (preferência sobre só FTP):** quando houver VT1/VT2 recentes, definir as zonas do atleta ancoradas neles (3 zonas: <VT1, VT1–VT2, >VT2) em vez de só %FTP. `zones_calculator` ganharia uma função `ventilatory_zones(vt1, vt2)` paralela à `power_zones(ftp)`. O recomendador usaria as zonas ventilatórias quando disponíveis, caindo para FTP quando não.
- **Monitorar VO2max ao longo da temporada:** incluir a série `vo2max_history` no Digital Twin / perfil (Tarefa 2) e no `twin_seed`; sinalizar tendência (subindo/estável/caindo) como contexto para o recomendador.
- **Detectar fadiga respiratória:** comparar V̇E/BR para uma dada potência contra o baseline do atleta dentro da sessão (deriva respiratória) e entre sessões; alimentar os guardrails (`safety_rules.md`) como mais um sinal de sobrecarga, junto de TSB/HRV/sono.
- **Confiança e explicabilidade (alinha com §12.4 da metodologia):** quando a recomendação usa zonas ventilatórias medidas, citar isso como evidência ("baseado no seu VT2 medido em DD/MM"), reforçando a confiança.

## 4. Estratégia de integração (futuro)

- **Formato de export do Tymewear:** provavelmente arquivos de atividade (FIT/CSV) com os streams de V̇E/BR + um resumo de teste rampa (VT1/VT2/VO2max). Confirmar o formato real antes de implementar.
- **Importador dedicado:** um `tymewear_importer.py` paralelo aos `fit/tcx/gpx_importer`, convertendo para o `NormalizedActivity` — que ganharia campos opcionais `ventilation_stream` / `breathing_rate_stream` (default vazio, como os streams atuais). `ingestion_service._persist_activity` persistiria esses streams nas novas colunas de `workout_streams`.
- **Detecção de teste rampa:** identificar sessões que são testes rampa (protocolo incremental) para extrair VT1/VT2/VO2max → `respiratory_metrics` + `vo2max_history`.
- **Sincronização:** começar por upload manual do export (como o onboarding TrainingPeaks da Tarefa 4); sync automático (API do Tymewear, se houver) é evolução posterior.

## 5. Pontos de extensão já mapeados (sem implementar)

| Onde | Extensão futura |
|------|-----------------|
| `models/workout.py::WorkoutStream` | colunas array `ventilation`, `breathing_rate` |
| `models/metrics.py` | nova `RespiratoryMetric`; nova `Vo2maxHistory` (espelho de `FtpHistory`) |
| `services/ingestion/normalizer.py::NormalizedActivity` | campos `ventilation_stream`, `breathing_rate_stream` (default vazio) |
| `services/ingestion/` | novo `tymewear_importer.py`; registrar no `_PARSERS` por formato |
| `services/metrics/zones_calculator.py` | `ventilatory_zones(vt1, vt2)` ao lado de `power_zones(ftp)` |
| `services/ai` (recomendador / digital twin) | preferir zonas ventilatórias; incluir tendência de VO2max; deriva respiratória nos guardrails |

> Nenhuma dessas mudanças é feita agora. Este documento é a referência de design
> para quando a feature Tymewear for priorizada. Não substitui avaliação médica.
