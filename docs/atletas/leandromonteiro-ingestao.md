# Relatório de Ingestão — Leandro Monteiro (TrainingPeaks)

> Estatísticas agregadas da ingestão do histórico real (Tarefa 1, prompt-02). Os
> dados brutos do atleta NÃO são versionados (`docs/data-atletas/` está no
> `.gitignore`); este relatório contém apenas números agregados, seguro de commitar.
> Gerado por `app.scripts.import_athlete` em 2026-06-24.

## Origem

- Pasta: `docs/data-atletas/leandromonteiro/` — exports padrão do TrainingPeaks.
- Períodos: `TP-2025/` (2025-01-01 a 2025-12-31) e `TP-2026/` (2026-01-01 a 2026-06-23, parcial).
- Cada período traz três zips: `MetricsExport` (metrics.csv, formato longo),
  `WorkoutExport` (workouts.csv, formato largo) e `WorkoutFileExport`
  (arquivos brutos `.fit/.tcx/.gpx` gzipados).
- `source = "trainingpeaks_export"` em todos os registros.

## Resultado da ingestão

| Métrica | Valor |
|---|---|
| Período coberto | 2025-01-01 → 2026-06-23 |
| Treinos executados | 424 |
| Treinos planejados | 393 |
| Dias de descanso (Day Off) | 102 |
| Dias com recovery (HRV/sono/RHR) | 486 |
| Dias com subjetivo (Notes) | 486 |
| Duplicados pulados | 415 |
| Cobertura de potência | 94,8% |
| Cobertura de FC | 93,4% |
| Cobertura de HRV | 100,0% |
| Anomalias detectadas | 0 |

Contagens conferidas no banco: 424 `workouts_completed`, 393 `workouts_planned`,
486 `recovery_metrics`, 407 `workout_streams` (treinos com séries por-segundo
vindas dos arquivos brutos), 392 treinos com potência média.

## Deduplicação (cross-source)

Os 415 "duplicados pulados" refletem o dedup correto entre o **resumo** de cada
treino (workouts.csv) e o **arquivo bruto** correspondente (.fit/.tcx/.gpx do
WorkoutFileExport): a mesma sessão aparece nas duas fontes. A chave de dedup
cross-source é `(data, duração)` — distância NÃO entra (varia entre fontes por
suavização de GPS / arredondamento do TP / "total" vs "moving"). Quando a sessão
existe nas duas fontes, mantemos a linha do arquivo bruto (que carrega as séries
por-segundo). Treinos distintos no mesmo dia/duração são preservados via um
discriminador de distância/nome (dedup intra-CSV). A ingestão é idempotente:
rodar de novo cria 0 registros novos (dedup por hash de conteúdo + chave natural).

## Campos não mapeados (reportados, não armazenados)

O `MetricsExport` traz estágios de sono granulares que o modelo atual não
modela (mapeamos apenas HRV, RHR/Pulse, horas de sono e Notes):

- `Number Times Woken`, `Time In Light Sleep`, `Time In REM Sleep`,
  `Time In Deep Sleep`, `Time Awake` — ~592 leituras cada.

CTL/ATL/TSB **não** vêm no export — são derivados pelo nosso motor de métricas
(`recompute_load_metrics`), nunca importados como dado real. Peso e métricas
subjetivas estruturadas (fadiga/soreness/humor) não constam neste export.

## Observações para a Tarefa 2 (perfil / engenharia reversa)

- Base rica para análise: 2 anos quase completos, alta cobertura de potência e FC,
  HRV diário, e os comentários do treinador (`CoachComments`) + do atleta
  (`AthleteComments`) preservados em `workouts_completed.extra` para extração de
  metodologia.
- Modalidades observadas no histórico: Bike, MTB, Strength, Swim (mapeadas para
  `sport`); intensidade classificada por IF.
- FTP do atleta ainda não definido para este registro → definir antes de análises
  de zonas/W·kg⁻¹ na Tarefa 2 (TSS aqui usa o valor de origem do TrainingPeaks).
