# Onboarding do histórico — exportar do TrainingPeaks

Este guia explica como trazer seu histórico do TrainingPeaks para o Athlete AI
Training Hub. Quanto mais completo o histórico, mais o sistema entende o seu
treino — e mais confiáveis ficam as recomendações.

> Seus dados são **isolados**: o histórico de um atleta nunca se mistura ao de
> outro nem à base de conhecimento geral.

---

## 1. O que exportar (3 arquivos)

No TrainingPeaks, exporte **três** conjuntos de dados do período desejado (idealmente os últimos 1–2 anos):

1. **Metrics Export** → gera um `.zip` com `metrics.csv` (métricas diárias: HRV, FC de repouso, horas de sono, etc.).
2. **Workout Export** → gera um `.zip` com `workouts.csv` (um registro por treino: planejado e executado, potência, FC, TSS, IF, zonas, comentários do treinador).
3. **Workout File Export** → gera um `.zip` com os arquivos brutos de cada atividade (`.fit`, `.tcx`, `.gpx`), que contêm os dados por segundo (potência, FC, cadência, GPS).

### Como gerar no TrainingPeaks
1. Entre na sua conta em trainingpeaks.com (conta de atleta).
2. Acesse a área de **exportação de dados** da conta (Settings/Account → exportação de dados; a localização exata varia conforme o plano/idioma da conta).
3. Selecione o **período** (ex.: 01/01 a 31/12 de cada ano) e gere os três exports: **Metrics**, **Workout** e **Workout File**.
4. Baixe os três `.zip`. Repita por ano se quiser cobrir 2 temporadas (ex.: uma pasta por ano).

> Não é preciso descompactar nada. Envie os `.zip` como estão.

---

## 2. Enviar para o sistema

Envie os `.zip` exportados para o endpoint de onboarding (multipart):

```
POST /api/v1/imports/trainingpeaks-export
Authorization: Bearer <seu token>
Content-Type: multipart/form-data
files: <MetricsExport-*.zip> <WorkoutExport-*.zip> <WorkoutFileExport-*.zip> [...]
```

Pode enviar os três tipos de uma vez (e de mais de um ano). O sistema identifica
cada arquivo pelo nome (`MetricsExport…`, `WorkoutExport…`, `WorkoutFileExport…`).

> **Nota técnica:** hoje o processamento é **síncrono** (adequado à fase de
> validação). Para uploads históricos muito grandes, o caminho futuro é uma fila
> assíncrona (Celery; ver `app/jobs/import_job.py`).

---

## 3. O que o sistema faz automaticamente

1. **Ingestão (pipeline da Tarefa 1):** descompacta, parseia os três tipos,
   normaliza para o modelo central, deduplica (a mesma sessão que aparece no
   resumo `workouts.csv` e no arquivo bruto é mesclada, não duplicada) e é
   **idempotente** (reenviar não duplica). CTL/ATL/TSB são recomputados.
2. **Perfil (análise da Tarefa 2):** gera o perfil do atleta e a "semente do
   Digital Twin" — curva de potência, FTP estimado, distribuição de intensidade,
   blocos de treino detectados, provas e janelas de taper, termos recorrentes dos
   comentários do treinador. (Dados de medidor fisiologicamente impossíveis, ex.:
   potência de medidor com defeito, são descartados.)
3. **Índice de riqueza de dados:** calcula o quão completo é o seu histórico
   (anos cobertos, % com potência, % com HRV/sono, nº de treinos) → rótulo
   **baixa / média / alta**. Esse índice **calibra a confiança** das recomendações
   da IA: quanto mais rico o histórico, mais específicas elas ficam.

A resposta do endpoint traz: o **relatório de ingestão** (treinos, métricas,
cobertura), o **índice de riqueza** e um **resumo do perfil** (FTP estimado,
nº de blocos e provas detectados).

---

## 4. Formatos futuros (planejado — ainda não implementado)

O onboarding via export do TrainingPeaks é o único disponível agora. Estão
previstos como evolução (design apenas):

- **Strava** — via API/OAuth (atividades e streams).
- **Garmin Connect** — via export ou API.
- **Intervals.icu** — via API/CSV.

Cada um seria normalizado para o mesmo modelo central e passaria pelo mesmo
pipeline de ingestão e geração de perfil, preservando o isolamento por atleta.

---

> Este onboarding é apoio à decisão baseado no seu histórico real. Não substitui
> avaliação médica ou profissional.
