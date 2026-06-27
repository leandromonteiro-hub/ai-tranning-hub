# Prompt 02 — Ingestão de Histórico e Construção do Perfil do Atleta

> Prompt complementar ao `prompt-athlete-ai-training-hub.md`.
> Objetivo: ingerir 2 anos de dados reais do TrainingPeaks de um atleta, fazer engenharia reversa da metodologia do treinador atual, construir o perfil/Digital Twin inicial e gerar confiança para a transição do treinamento humano para o treinamento via IA.
> Cole o bloco abaixo no Claude Code, na mesma sessão/repositório onde o sistema do Prompt 01 foi criado.

---

```text
Este é um prompt de continuação do projeto "Athlete AI Training Hub". O esqueleto do sistema (FastAPI, PostgreSQL, modelos, ingestão, métricas, guardrails e camada de IA) já foi definido no prompt anterior. Agora vamos usar DADOS REAIS de um atleta para validar a ingestão e construir o primeiro perfil completo.

═══════════════════════════════════════════════════
OBJETIVO DESTE PROMPT
═══════════════════════════════════════════════════

1. Ingerir 2 anos de dados históricos reais do TrainingPeaks de um atleta.
2. Fazer engenharia reversa da metodologia aplicada pelo treinador atual.
3. Construir o perfil completo do atleta (semente do Digital Twin Athlete).
4. Identificar padrões de periodização, preparação pré-prova, melhores marcas e respostas individuais ao treino.
5. Gerar um relatório que conecte decisões passadas do treinador a conceitos de treinamento — para que o atleta confie que a IA entende o que vinha sendo feito e por quê, antes de assumir a prescrição.
6. Preparar o fluxo de onboarding de dados históricos pensando no futuro comercial.

CONTEXTO HUMANO IMPORTANTE:
O atleta vai DESCARTAR o treinador atual e passar a treinar pela IA. Para ele sentir confiança, o sistema precisa demonstrar que:
- Entendeu a metodologia que vinha sendo aplicada.
- Sabe explicar por que o treinador fez certas escolhas em momentos específicos (ex.: bloco de base no início da temporada, semana regenerativa após bloco intenso, taper antes de prova alvo).
- Consegue dar continuidade respeitando o que funcionou, ajustando o que não funcionou, com base em evidência do próprio histórico.
Não critique o treinador anterior gratuitamente. O tom deve ser de continuidade inteligente e respeitosa, destacando acertos e oportunidades de melhoria sustentadas por dados.

═══════════════════════════════════════════════════
LOCALIZAÇÃO E ESTRUTURA DOS DADOS
═══════════════════════════════════════════════════

Os dados estão em: C:\projetos\treinador-ciclismo\docs\data-atletas

Estrutura atual (1 atleta de teste):

docs/data-atletas/
  leandromonteiro/
    TP-2025/
      MetricsExport-monteiro-leandro-2025-01-01-2025-12-31.zip
      WorkoutExport-monteiro-leandro-2025-01-01-2025-12-31.zip
      WorkoutFileExport-monteiro-leandro-2025-01-01-2025-12-31.zip
    TP-2026/
      MetricsExport-monteiro-leandro-2026-01-01-2026-06-23.zip
      WorkoutExport-monteiro-leandro-2026-01-01-2026-06-23.zip
      WorkoutFileExport-monteiro-leandro-2026-01-01-2026-06-23.zip

São os exports padrão do TrainingPeaks. Para cada período há três tipos de export:

1. MetricsExport (.zip → CSV): métricas diárias do atleta. Tipicamente contém data e colunas como peso, FC de repouso, HRV, horas de sono, fadiga, stress, soreness/dor, humor, e os valores do Performance Management Chart (CTL, ATL, TSB/Form). Os nomes exatos das colunas variam por idioma/conta — detecte dinamicamente e normalize.

2. WorkoutExport (.zip → CSV): um registro por treino, com treino planejado e/ou executado. Tipicamente: data, título, tipo de treino (WorkoutType), modalidade, duração planejada e executada, distância, elevação, TSS, IF, NP, potência média/máxima, FC média/máxima, cadência, kJ, calorias, RPE, e descrição/comentários (frequentemente onde o treinador escreve o objetivo e o feedback do treino). Os comentários do treinador são uma fonte rica para inferir a metodologia.

3. WorkoutFileExport (.zip → arquivos brutos): os arquivos de cada atividade (.fit, .pwx, .tcx, .gpx). Contêm os streams por segundo (potência, FC, cadência, velocidade, altitude, GPS).

IMPORTANTE SOBRE OS DADOS:
- Não há garantia de que toda atividade tenha todos os campos (nem todo treino tem potência, por exemplo).
- Pode haver treinos planejados sem execução e execuções sem planejamento.
- Pode haver duplicatas entre o resumo CSV e o arquivo bruto — deduplicar por data + duração + hash do arquivo.
- O ano de 2026 é parcial (até 23/06).
- Trate fuso horário, unidades (km vs mi, kg vs lb) e datas de forma robusta.

═══════════════════════════════════════════════════
TAREFA 1 — PIPELINE DE INGESTÃO DOS EXPORTS DO TRAININGPEAKS
═══════════════════════════════════════════════════

Implemente um importador específico para o formato de export do TrainingPeaks que:

1. Receba o caminho de uma pasta de atleta (ex.: docs/data-atletas/leandromonteiro).
2. Descompacte os .zip em uma área de trabalho temporária (não comitar os dados extraídos).
3. Detecte e parseie os três tipos de export (Metrics, Workout, WorkoutFile).
4. Normalize tudo para o modelo de dados central já definido (workouts_planned, workouts_completed, workout_streams, recovery_metrics, body_metrics, subjective_metrics, ftp_history, etc.).
5. Faça deduplicação e validação de qualidade.
6. Vincule cada registro ao athlete_id correto, respeitando o isolamento multi-tenant.
7. Registre origem (source = "trainingpeaks_export"), arquivo original e qualidade do dado.
8. Seja idempotente: rodar duas vezes não duplica dados.
9. Gere um relatório de ingestão: quantos treinos, quantas métricas diárias, período coberto, campos ausentes, taxa de cobertura de potência/FC/HRV, anomalias detectadas.

Crie um comando CLI / script (ex.: `make import-athlete ATHLETE=leandromonteiro` ou um script Python) para rodar a ingestão de uma pasta inteira de uma vez.

Escreva testes com uma amostra pequena e anonimizada (não comitar dados reais do atleta no repositório — adicionar docs/data-atletas/ ao .gitignore).

═══════════════════════════════════════════════════
TAREFA 2 — ANÁLISE E ENGENHARIA REVERSA DA METODOLOGIA
═══════════════════════════════════════════════════

Depois da ingestão, gere uma análise automatizada do histórico que produza:

PERFIL DO ATLETA
- Modalidade principal e secundárias (inferidas pelos tipos de treino).
- Volume semanal médio (horas, distância, TSS) e variação ao longo do tempo.
- Distribuição de intensidade (tempo por zona de potência e de FC; classificar como polarizado, piramidal ou sweet spot).
- FTP estimado/declarado ao longo do tempo e evolução de W/kg.
- Curva de potência histórica e melhores marcas (5s, 1min, 5min, 20min, 60min).
- Métricas de recuperação disponíveis (HRV, sono, RHR) e correlação com performance.

ENGENHARIA REVERSA DA METODOLOGIA DO TREINADOR
- Detecte os blocos de treinamento ao longo dos 2 anos (base, build, peak, taper, recovery) a partir da dinâmica de CTL/ATL/TSB, volume e intensidade.
- Identifique o padrão de carga: razão trabalho/recuperação, duração típica dos mesociclos, frequência de semanas regenerativas, taxa de progressão de carga semana a semana.
- Identifique a distribuição de tipos de treino por fase (quanto de Z2, threshold, VO2max, sprint, força etc. em cada período).
- Extraia padrões dos comentários/descrições dos treinos (objetivos recorrentes, terminologia, estrutura de intervalos prescrita).

METODOLOGIA PRÉ-PROVA (TAPER)
- Identifique as provas no histórico (a partir de tipo de treino "Race", títulos, ou picos de intensidade/resultado).
- Para cada prova relevante, reconstrua a janela de 2 a 3 semanas anteriores: como CTL, ATL, TSB e volume se comportaram, qual foi a estratégia de taper, e qual foi o resultado/performance.
- Compare diferentes tapers e correlacione com as melhores e piores performances.

MELHORES MARCAS E PADRÕES DE PERFORMANCE
- Liste as melhores performances (potência, resultado em prova, recordes de curva de potência).
- Para cada uma, descreva o bloco de treino que a antecedeu (o "caminho" até o pico).
- Identifique padrões pré-pico e padrões pré-queda/fadiga/lesão (se houver sinais nos dados subjetivos/HRV).

CORRELAÇÃO COM DECISÕES DO TREINADOR (camada de confiança)
- Para momentos-chave, gere explicações no formato:
  "Em [data], seu treinador aplicou [tipo de bloco/treino]. Isso é coerente com [conceito de treinamento], e nos seus dados resultou em [efeito observado: ganho de CTL, melhora de FTP, boa prova, etc.]."
- Destaque o que funcionou bem e merece ser mantido.
- Aponte, com cautela e baseado em evidência, oportunidades de ajuste (ex.: monotonia alta, recuperação insuficiente, intensidade mal distribuída) — sempre sustentado pelos dados, nunca como crítica gratuita.

ENTREGÁVEL DE ANÁLISE
- Um relatório legível (docs/atletas/leandromonteiro-perfil.md) com todas as seções acima.
- Os mesmos dados estruturados gravados no banco como semente do Digital Twin Athlete.
- Um resumo executivo de 1 página que o atleta possa ler e pensar "o sistema entende meu treino melhor do que eu esperava".

═══════════════════════════════════════════════════
TAREFA 3 — FUNDAMENTAÇÃO CIENTÍFICA (ARTIGOS)
═══════════════════════════════════════════════════

Leia (fetch) e incorpore o que for relevante destes materiais. Documente em docs/training_methodology.md as decisões de design que cada um influenciou. Avalie criticamente o que se aplica ao nosso caso (ciclismo/MTB, dados reais, 1 atleta inicialmente).

1. Towards an AI-Based Tailored Training Planning for Road Cyclists: A Case Study
   https://www.mdpi.com/2076-3417/11/1/313
   Foco: como estruturar planejamento de treino individualizado por IA a partir de dados de ciclistas; quais features/modelagem usaram; como validaram. Extraia o que for aproveitável para nossa Training Intelligence Layer.

2. Acceptance and trust in AI-generated exercise plans among recreational athletes
   https://pmc.ncbi.nlm.nih.gov/articles/PMC11908068/
   Foco: o que faz atletas CONFIAREM em planos gerados por IA. Isto é central para a nossa transição (atleta deixando o treinador humano). Traduza os achados em requisitos de produto: explicabilidade, transparência, controle do usuário, linguagem, validação. Liste como requisitos concretos de UX e de design das recomendações.

3. AI Cycling Coach - Is It the Future of Training? (vídeo)
   https://www.youtube.com/watch?v=deHrsG-En6w
   Foco: percepção de mercado, expectativas e limitações de coaches de IA no ciclismo. Use para calibrar posicionamento e evitar promessas excessivas. (Se não conseguir acessar o conteúdo do vídeo, registre isso e siga.)

Para cada artigo, escreva: principais achados, o que adotamos, o que descartamos e por quê.

═══════════════════════════════════════════════════
TAREFA 4 — ONBOARDING DE DADOS HISTÓRICOS (VISÃO COMERCIAL)
═══════════════════════════════════════════════════

Pensando na futura comercialização, projete e implemente o início de um fluxo de onboarding para que QUALQUER novo atleta traga seu histórico e o sistema fique mais inteligente:

- Documente o passo a passo para o atleta exportar os dados do TrainingPeaks (Metrics, Workout e WorkoutFile) — um guia simples em docs/onboarding-trainingpeaks.md.
- Endpoint/feature de upload dos .zip de export, que dispara o pipeline da Tarefa 1 automaticamente.
- Após a ingestão, gerar automaticamente o perfil da Tarefa 2 para o novo atleta.
- Garantir isolamento total: o histórico de um atleta nunca contamina o de outro nem a base de conhecimento.
- Pensar em formatos adicionais de onboarding futuro (Strava, Garmin, Intervals.icu) mas implementar agora apenas o de TrainingPeaks export.
- Definir um "índice de riqueza de dados" por atleta (quão completo é o histórico: anos cobertos, % com potência, % com HRV/sono), usado para calibrar a confiança das recomendações da IA.

═══════════════════════════════════════════════════
TAREFA 5 — FEATURE FUTURA: TYMEWEAR (MÉTRICAS RESPIRATÓRIAS / VO2MAX)
═══════════════════════════════════════════════════

Não implementar agora, mas projetar a arquitetura para acomodar depois. Já temos atletas usando o dispositivo Tymewear, que fornece métricas respiratórias (ventilação, frequência respiratória, limiares ventilatórios) e estimativa de VO2max de campo.

Materiais de referência:
- https://www.tymewear.com/blogs/validation-studies/tymewear-internal-validation-study-of-breathing-metrics
- https://www.tymewear.com/pages/training-ebook
- https://www.tymewear.com/pages/vo2max-explained

Entregáveis desta tarefa (apenas design/documentação, em docs/feature-tymewear.md):
- Quais métricas respiratórias o Tymewear fornece e como elas complementam potência e FC (ex.: detecção de limiares ventilatórios VT1/VT2, deriva respiratória, VO2max de campo, eficiência respiratória).
- Como modelar essas métricas no banco (novas colunas em workout_streams e/ou nova tabela respiratory_metrics; nova série temporal de VO2max).
- Como a Training Intelligence Layer usaria esses dados (ex.: definição de zonas por limiares ventilatórios em vez de só FTP; monitorar VO2max ao longo da temporada; detectar fadiga respiratória).
- Estratégia de integração de dados (formato de export do Tymewear, sincronização).
- Deixar pontos de extensão no schema e nos serviços já preparados, sem implementar a ingestão agora.

═══════════════════════════════════════════════════
ORDEM DE EXECUÇÃO E SAÍDAS ESPERADAS
═══════════════════════════════════════════════════

1. Confirme/ajuste o modelo de dados se necessário para suportar os exports reais do TrainingPeaks.
2. Implemente o importador de export do TrainingPeaks (Tarefa 1) + testes + script de execução.
3. Rode a ingestão dos dados de leandromonteiro e gere o relatório de ingestão.
4. Implemente a análise/engenharia reversa (Tarefa 2) e gere o perfil do atleta + resumo executivo.
5. Incorpore a fundamentação dos artigos (Tarefa 3) na documentação e nos requisitos das recomendações.
6. Implemente o início do onboarding de dados históricos (Tarefa 4).
7. Documente o design da feature Tymewear (Tarefa 5).

REGRAS:
- Não comitar dados reais do atleta (adicionar docs/data-atletas/ ao .gitignore).
- Manter separação entre dado real, dado inferido e conhecimento geral.
- Toda inferência de metodologia deve apontar a evidência no histórico que a sustenta.
- Linguagem do relatório do atleta em português; código em inglês.
- Não prometer resultados; posicionar como apoio à decisão baseado no histórico real do atleta.

COMECE pela Tarefa 1. Se precisar tomar decisões de design para lidar com o formato real dos exports, tome e justifique. Não pare no meio das tarefas.
```
