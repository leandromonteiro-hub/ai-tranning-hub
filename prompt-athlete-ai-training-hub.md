# Prompt — Athlete AI Training Hub

> Versão melhorada para uso no Claude Code / Cursor Agent.
> Contexto: validar o sistema com 2 atletas antes de qualquer decisão comercial.

---

```text
Você vai atuar como arquiteto de software sênior, engenheiro de dados e especialista em IA aplicada a treinamento esportivo de endurance e ciclismo de alto rendimento.

═══════════════════════════════════════════════════
CONTEXTO E MOTIVAÇÃO
═══════════════════════════════════════════════════

Treino mountain bike há mais de 10 anos com diferentes treinadores. Usei o TrainingPeaks para receber treinos prescritos, registrar execuções, acompanhar carga, evolução, provas, campeonatos e métricas fisiológicas. Tenho entre 5 e 6 anos de dados históricos acumulados nessa plataforma.

Quero construir um sistema próprio de gestão de treinamento orientado por IA, capaz de analisar meus dados históricos e auxiliar no planejamento, ajuste e acompanhamento de treinos de mountain bike de forma personalizada.

A inspiração são metodologias de treinadores de referência mundial do ciclismo, incluindo conceitos de alto rendimento, World Tour, endurance, periodização, potência, recuperação, tapering e preparação para provas.

O sistema não substitui avaliação médica ou profissional. Funciona como ferramenta inteligente de apoio à análise, planejamento e tomada de decisão.

═══════════════════════════════════════════════════
CONTEXTO CRÍTICO DE DESENVOLVIMENTO
═══════════════════════════════════════════════════

ANTES de qualquer aspecto comercial, o objetivo imediato é VALIDAR o sistema com exatamente 2 atletas reais. Só após essa validação prática o sistema será avaliado para comercialização.

Isso significa que:
- A primeira versão deve funcionar MUITO BEM para 2 pessoas, não razoavelmente bem para mil.
- A arquitetura deve suportar múltiplos atletas com isolamento total de dados desde o início.
- A experiência dos 2 atletas de teste é mais importante do que qualquer feature extra.
- Coleta de feedback dos atletas deve ser um componente de primeira classe no sistema.
- Complexidade e custo de infraestrutura devem ser mínimos nesta fase.
- Nada deve ser "over-engineered" antes de validação real.

Critérios de sucesso da fase de validação:
1. Os 2 atletas conseguem importar seus dados históricos sem precisar de suporte técnico.
2. As recomendações geradas fazem sentido para atletas experientes.
3. Os atletas usam o sistema voluntariamente por pelo menos 4 semanas consecutivas.
4. O feedback coletado é positivo o suficiente para justificar evolução do produto.
5. Nenhum dado se mistura entre os dois atletas (isolamento total verificado).

═══════════════════════════════════════════════════
NOME DO SISTEMA
═══════════════════════════════════════════════════

Athlete AI Training Hub

═══════════════════════════════════════════════════
OBJETIVO GERAL
═══════════════════════════════════════════════════

Criar um sistema modular que consolide dados esportivos, fisiológicos, competitivos e subjetivos do atleta em um banco de dados centralizado, permitindo que uma camada de IA analise o histórico individual e gere recomendações explicáveis de treino.

O sistema é baseado nos conceitos:
1. Athlete Data Hub — repositório central e único de verdade do atleta
2. Digital Twin Athlete — representação computacional do atleta e seu histórico
3. Training Intelligence Layer — camada de IA sobre o histórico real
4. RAG sobre histórico esportivo — busca semântica em dados do próprio atleta
5. Recomendações explicáveis e rastreáveis — toda sugestão tem justificativa e evidência

Princípios inegociáveis:
- Segurança do atleta acima de qualquer otimização de performance.
- Progressão gradual, baseada em evidências do próprio histórico.
- Individualização real, não templates genéricos.
- Rastreabilidade total de cada decisão da IA.
- Separação explícita entre dados reais e sugestões inferidas.
- Toda recomendação pode ser rejeitada ou ajustada pelo atleta.
- O sistema aprende com o feedback posterior às recomendações.

═══════════════════════════════════════════════════
ESCOPO FUNCIONAL COMPLETO
═══════════════════════════════════════════════════

O sistema deve ser capaz de:

INGESTÃO DE DADOS
- Importar arquivos FIT, TCX, GPX, CSV e JSON.
- Importar dados históricos exportados do TrainingPeaks.
- Suportar upload manual de arquivos em lote.
- Detectar e ignorar duplicatas automaticamente.
- Validar qualidade dos dados importados.
- Registrar origem e metadados de cada dado importado.
- Integrar futuramente via API com: TrainingPeaks, Garmin Connect, Strava, Intervals.icu, Wahoo, Polar, Coros, Oura Ring, Whoop, Apple Health, Google Health Connect.

ARMAZENAMENTO E MODELAGEM
- Treinos planejados e treinos executados (separados e relacionáveis).
- Métricas fisiológicas detalhadas por atividade.
- Zonas de potência e frequência cardíaca com histórico de versões.
- FTP histórico com data de vigência de cada valor.
- Peso, sono, HRV, recuperação e fadiga.
- Calendário competitivo com provas alvo e secundárias.
- Objetivos de curto, médio e longo prazo.
- Disponibilidade semanal e restrições de agenda.
- RPE, humor, sensação, dor, lesão e comentários subjetivos.
- Streams de dados brutos de atividades (potência, FC, cadência por segundo).

CÁLCULO E ANÁLISE
- Carga aguda (ATL), carga crônica (CTL), balance de treinamento (TSB).
- Monotonia e strain de Foster.
- TSS, IF, NP, kJ por atividade.
- Curva de potência histórica e por período.
- Melhores potências em 5s, 1min, 5min, 20min, 60min.
- W/kg histórico.
- Decoupling aeróbico.
- Eficiência aeróbica.
- Detecção automática de períodos: base, build, peak, taper, recovery.
- Identificação de padrões de resposta ao treinamento.
- Correlação entre tipos de treino e evolução de performance.

PLANEJAMENTO
- Sugestões de microciclos, mesociclos e macrociclos.
- Plano semanal, mensal e para prova alvo.
- Ajuste automático baseado em fadiga, sono, recuperação e disponibilidade.
- Alertas de risco de excesso de carga com nível: baixo, moderado, alto.
- Em risco alto: sugestão automática de alternativa mais conservadora.

IA E RECOMENDAÇÕES
- Responder perguntas em linguagem natural sobre o histórico do atleta.
- Gerar recomendações explicáveis com justificativa estruturada.
- Comparar cada sugestão com treinos semelhantes do passado do atleta.
- Validar segurança da carga antes de qualquer recomendação.
- Registrar: recomendação, justificativa, evidências, modelo usado, confiança, riscos.
- Registrar decisão do atleta sobre a recomendação (aceita, rejeitada, modificada).
- Registrar feedback posterior do atleta sobre o resultado.

FEEDBACK E VALIDAÇÃO
- Interface para o atleta avaliar cada recomendação após execução.
- Dashboard de feedbacks para o administrador do sistema.
- Métricas de qualidade das recomendações ao longo do tempo.
- Exportação de dados de feedback para análise.

═══════════════════════════════════════════════════
PESQUISA DE APIs E INTEGRAÇÕES
═══════════════════════════════════════════════════

Antes de definir a arquitetura final, pesquise e documente as opções de integração com as seguintes plataformas.

PLATAFORMAS DE TREINO
- TrainingPeaks, Garmin Connect, Strava, WKO5, Intervals.icu, TrainerRoad, Today's Plan, Golden Cheetah

DISPOSITIVOS
- Garmin, Wahoo, Hammerhead Karoo, Polar, Coros, Suunto

SAÚDE E RECUPERAÇÃO
- Oura Ring, Whoop, Apple Health, Google Health Connect, Fitbit

Para cada plataforma, documente:
- API oficial? Pública ou restrita?
- SDK disponível?
- Modelo de autenticação (OAuth, API Key, outro)?
- Dados acessíveis via API?
- Limites de uso e custo?
- Restrições comerciais relevantes?
- Webhook disponível?
- Formatos de exportação manual (FIT, TCX, GPX, CSV, JSON)?
- Risco de bloqueio ou mudança unilateral de API?
- Estratégia recomendada para integração inicial?

Gere uma matriz comparativa com colunas:
Plataforma | Tipo de dado | API oficial | OAuth | Webhook | Formatos de exportação | Facilidade de integração | Risco de bloqueio | Custo | Prioridade para MVP de validação | Estratégia recomendada

Para plataformas com API restrita ou indisponível, proponha alternativas:
importação manual de arquivo, upload de export, sincronização via pasta monitorada, conector de terceiros ou integração posterior quando viável.

═══════════════════════════════════════════════════
ARQUITETURA MULTI-ATLETA E ISOLAMENTO DE DADOS
═══════════════════════════════════════════════════

O sistema deve suportar múltiplos atletas desde o início, com isolamento total entre eles.

Requisitos de isolamento:
- Cada atleta possui um tenant_id único.
- Nenhuma query deve retornar dados de um atleta para outro.
- Toda operação de escrita valida o tenant_id no nível do serviço, não apenas da rota.
- Logs de auditoria registram qual usuário acessou quais dados.
- A IA nunca mistura histórico de atletas diferentes, mesmo que os perfis sejam similares.
- Soft delete com timestamp: nenhum dado é apagado permanentemente.
- Campos sensíveis são separados em tabela dedicada com controle de acesso adicional.

Modelo de usuários e permissões:
- Papel ADMIN: acesso total, incluindo dados de todos os atletas, métricas de uso, feedbacks.
- Papel ATHLETE: acesso apenas aos próprios dados.
- Papel COACH (futuro): acesso somente-leitura aos atletas vinculados.
- Autenticação via JWT com refresh token.
- Endpoints de admin separados, protegidos por role e prefixo de rota (/admin/).

═══════════════════════════════════════════════════
MODELO DE DADOS
═══════════════════════════════════════════════════

Implemente o schema com as seguintes tabelas. Cada tabela deve ter: id (UUID), created_at, updated_at, deleted_at (soft delete), created_by e athlete_id quando aplicável.

ATLETA E PERFIL
- athletes: dados básicos, credenciais de acesso, role, tenant_id
- athlete_profiles: dados fisiológicos e esportivos do atleta
- athlete_goals: objetivos com prazo, tipo, status e progresso
- athlete_availability: disponibilidade semanal e restrições recorrentes

FONTES E IMPORTAÇÃO
- data_sources: plataformas e formatos de origem cadastrados
- imported_files: arquivos importados com hash para deduplicação, status de processamento, erros

TREINOS
- workouts_planned: treinos prescritos com estrutura de intervalos
- workouts_completed: treinos executados com métricas calculadas
- workout_streams: streams brutos por segundo (potência, FC, cadência, altitude, velocidade)
- workout_intervals: intervalos detectados ou definidos por treino
- workout_metrics: métricas derivadas calculadas por treino

POTÊNCIA E ZONAS
- ftp_history: FTP histórico com data de início e fim de vigência
- power_zones: zonas de potência por período, baseadas no FTP vigente
- heart_rate_zones: zonas de FC por período
- power_curve: melhores esforços históricos por duração

MÉTRICAS FISIOLÓGICAS E RECUPERAÇÃO
- body_metrics: peso, IMC, composição corporal por data
- recovery_metrics: HRV, RHR, sono, recovery score por data
- subjective_metrics: RPE, humor, fadiga, dor, motivação, lesões por data

PROVAS E COMPETIÇÕES
- races: provas e campeonatos com dados gerais
- race_results: resultados do atleta em cada prova
- race_analyses: análise pré e pós-prova gerada ou escrita pelo atleta

PLANEJAMENTO E PERIODIZAÇÃO
- training_blocks: blocos de treinamento (base, build, peak, taper, recovery)
- training_weeks: semanas de treinamento com carga planejada e executada
- training_plans: planos gerados ou importados

CARGA E FORMA
- load_metrics: CTL, ATL, TSB, monotonia, strain calculados por data por atleta

IA E RECOMENDAÇÕES
- ai_recommendations: recomendações geradas com prompt versionado, modelo, confiança
- ai_recommendation_evidence: evidências históricas usadas em cada recomendação
- ai_recommendation_feedback: avaliação do atleta após execução (rating, comentário, resultado observado)
- ai_decisions: log de aceitação, rejeição ou modificação de cada recomendação

BASE DE CONHECIMENTO
- knowledge_documents: documentos da base de conhecimento com metadados
- embeddings: vetores de embeddings de treinos, provas, comentários e documentos
- prompt_templates: templates de prompt versionados com hash de conteúdo

SISTEMA
- audit_logs: log imutável de todas as operações com usuário, endpoint, payload resumido e IP
- system_config: configurações do sistema por ambiente

═══════════════════════════════════════════════════
DIGITAL TWIN ATHLETE
═══════════════════════════════════════════════════

O sistema deve construir e manter um Gêmeo Digital do Atleta, que representa:

- Histórico de treinamento e competições.
- Estado atual de forma (CTL), fadiga (ATL) e prontidão (TSB).
- Perfil fisiológico atual e evolução histórica.
- Resposta individual aos diferentes tipos de estímulo.
- Tolerância sustentável a volume e intensidade.
- Padrões de progressão e padrões de queda de performance.
- Risco atual de excesso de carga.
- Correlações pessoais: quais treinos melhoraram quais métricas.
- Padrões pré-performance: o que aconteceu nos blocos antes das melhores provas.
- Padrões pré-queda: sinais que antecederam lesões ou overreaching.

O gêmeo digital é atualizado a cada novo dado importado e é a fonte primária de contexto para todas as recomendações da IA.

═══════════════════════════════════════════════════
GUARDRAILS DE SEGURANÇA
═══════════════════════════════════════════════════

Antes de qualquer recomendação, o sistema DEVE validar:

- Carga da semana atual e das últimas 4 semanas.
- CTL atual e tendência.
- ATL atual.
- TSB atual (sinalizar se muito negativo).
- Sono das últimas 48 horas (se disponível).
- HRV das últimas 48 horas (se disponível).
- Fadiga subjetiva reportada (se disponível).
- Histórico de lesões recentes.
- Tempo disponível do atleta.
- Proximidade de prova alvo.
- Progressão em relação à semana anterior (máximo 10% de aumento de carga).
- Intensidade acumulada nos últimos 7 dias.
- Dias consecutivos com carga alta.

Classificação de risco:
- RISCO BAIXO: todos os indicadores dentro do esperado.
- RISCO MODERADO: 1 a 2 indicadores limítrofes, recomendação com aviso.
- RISCO ALTO: qualquer indicador crítico. Bloquear recomendação original e sugerir alternativa conservadora.

Toda recomendação deve incluir:
- Objetivo fisiológico do treino proposto.
- Relação com o bloco atual e com a prova alvo.
- Evidência no histórico do atleta que apoia a sugestão.
- Nível de confiança da recomendação (0 a 1, com justificativa).
- Riscos identificados.
- Como ajustar se o atleta estiver mais cansado no dia.
- Como ajustar se o atleta tiver menos tempo disponível.

═══════════════════════════════════════════════════
CAMADA DE IA (TRAINING INTELLIGENCE LAYER)
═══════════════════════════════════════════════════

A camada de IA deve usar:
- RAG sobre o histórico esportivo do atleta (busca semântica em embeddings).
- Consulta ao banco relacional para métricas calculadas.
- Consulta a séries temporais para carga, forma e fadiga.
- Regras fisiológicas codificadas como guardrails.
- Templates de prompt versionados e auditáveis.
- Registro completo de cada chamada ao LLM (prompt, resposta, modelo, tokens, custo estimado).
- Memória de contexto do atleta atualizada incrementalmente.

A IA deve responder em linguagem natural perguntas como:
- Como estou evoluindo nas últimas 8 semanas?
- Qual foi meu melhor bloco de treino antes de uma boa prova? O que tinha de diferente?
- Que tipo de treino mais melhorou meu FTP historicamente?
- Estou acumulando fadiga demais essa semana?
- Qual treino devo fazer amanhã dado meu cansaço atual?
- Como ajustar a semana se dormi mal nas últimas 2 noites?
- Como preparar uma prova daqui a 8 semanas partindo do estado atual?
- Qual taper funcionou melhor historicamente para mim?
- Estou fazendo intensidade demais em relação ao volume?
- Quais sinais aparecem antes das minhas melhores performances?
- Quais sinais aparecem antes de queda de performance ou lesão?

A IA deve gerar:
- Plano semanal detalhado com justificativa.
- Plano para prova alvo com periodização completa.
- Análise de bloco de treinamento concluído.
- Análise pós-prova.
- Ajuste diário baseado em dados recentes.
- Recomendação de recuperação ativa ou passiva.
- Alertas proativos de risco de excesso de carga.
- Relatório de evolução mensal.

═══════════════════════════════════════════════════
BASE DE CONHECIMENTO DE TREINAMENTO
═══════════════════════════════════════════════════

Criar base de conhecimento separada dos dados do atleta contendo conceitos de treinamento de endurance e ciclismo.

Conceitos a incluir na base inicial:
- Periodização clássica e periodização reversa.
- Polarized training, pyramidal training, sweet spot training.
- Zone 2, threshold, VO2max, anaerobic capacity, sprint training.
- Overload, recovery, tapering.
- CTL, ATL, TSB, FTP, Critical Power, Power Duration Curve.
- Aerobic decoupling, race specificity.
- Especificidades de MTB XCO, MTB XCM, gran fondo, road cycling, stage racing.
- Heat adaptation, altitude adaptation.
- Strength endurance para ciclismo.

A base de conhecimento é usada apenas como referência conceitual para a IA. Dados do atleta nunca são misturados com a base de conhecimento.

O sistema deve separar explicitamente:
1. Dados históricos reais do atleta.
2. Conhecimento geral de treinamento.
3. Regras internas e guardrails do sistema.
4. Recomendações geradas pela IA.
5. Feedback do atleta sobre as recomendações.

═══════════════════════════════════════════════════
STACK TÉCNICA
═══════════════════════════════════════════════════

Backend:
- Python 3.12+
- FastAPI com async/await
- SQLAlchemy 2.x com suporte async
- Pydantic v2
- Alembic para migrações

Banco de dados:
- PostgreSQL 16
- pgvector para embeddings
- TimescaleDB para séries temporais de streams e métricas por data (avaliar se compensa no MVP de validação versus PostgreSQL puro)

Processamento de dados:
- fitparse para arquivos FIT
- gpxpy para GPX
- lxml para TCX
- pandas e polars para transformações
- Celery + Redis para jobs assíncronos de importação e cálculo

IA:
- Camada de abstração de LLM (suportar OpenAI, Anthropic, e futuramente modelos locais)
- LangChain ou implementação própria de RAG — justificar a escolha
- pgvector como vector store
- Prompt templates versionados, armazenados no banco com hash de conteúdo
- Registro de todas as chamadas ao LLM com custo estimado

Frontend (MVP de validação):
- Streamlit ou Next.js — justificar qual faz mais sentido para validar com 2 atletas rapidamente
- Dashboard: calendário de treinos, gráfico de CTL/ATL/TSB, lista de recomendações, histórico de provas
- Interface de feedback: botão de avaliação em cada recomendação

Autenticação e segurança:
- JWT com refresh token
- Bcrypt para hash de senha
- Rate limiting por usuário
- Validação de tenant em todos os endpoints

Infraestrutura para validação:
- Docker e Docker Compose (rodar tudo localmente com um comando)
- Variáveis de ambiente via .env
- Sem dependência de serviços pagos externos no MVP de validação
- Estrutura preparada para deploy em cloud posteriormente

Observabilidade:
- Logs estruturados em JSON
- Registro de cada chamada ao LLM (prompt, resposta, latência, tokens, custo estimado)
- Health check endpoint

Testes:
- pytest com fixtures
- Testes de ingestão por formato (FIT, TCX, GPX, CSV)
- Testes de cálculo de métricas (CTL, ATL, TSB, TSS, IF)
- Testes de guardrails de segurança
- Testes de isolamento entre atletas
- Testes de API (FastAPI TestClient)
- Cobertura mínima: serviços críticos (ingestão, cálculo, guardrails) devem ter 80%+

═══════════════════════════════════════════════════
ESTRUTURA DE PASTAS
═══════════════════════════════════════════════════

athlete-ai-training-hub/
  backend/
    app/
      main.py
      core/
        config.py          # Settings com Pydantic BaseSettings
        database.py        # Engine, sessão async, dependency injection
        security.py        # JWT, bcrypt, middleware de auth
        tenant.py          # Middleware e validação de isolamento de tenant
        logging.py         # Configuração de logs estruturados
      models/
        base.py            # BaseModel com id UUID, timestamps, soft delete
        athlete.py
        workout.py
        race.py
        metrics.py
        training_plan.py
        ai.py
        knowledge.py
        audit.py
      schemas/
        athlete.py
        workout.py
        race.py
        metrics.py
        ai.py
        auth.py
      api/
        deps.py            # Dependencies compartilhadas (get_db, get_current_user, get_tenant)
        routes/
          auth.py
          athletes.py
          workouts.py
          races.py
          metrics.py
          recommendations.py
          imports.py
          feedback.py
          admin.py         # Rotas administrativas protegidas por role
      services/
        ingestion/
          fit_importer.py
          tcx_importer.py
          gpx_importer.py
          csv_importer.py
          normalizer.py
          deduplicator.py
          quality_validator.py
        metrics/
          load_calculator.py     # CTL, ATL, TSB
          tss_calculator.py      # TSS, IF, NP
          power_curve.py
          zones_calculator.py
          fatigue_analyzer.py
        ai/
          rag.py                 # Recuperação de contexto via embeddings
          recommender.py         # Orquestração de recomendações
          prompts.py             # Templates versionados
          safety_validator.py    # Guardrails antes de qualquer recomendação
          evidence_builder.py    # Coleta de evidências do histórico
          llm_client.py          # Abstração de LLM com logging
          digital_twin.py        # Construção e atualização do gêmeo digital
        knowledge/
          document_loader.py
          embedder.py
      repositories/
        base.py
        athlete_repo.py
        workout_repo.py
        metrics_repo.py
        ai_repo.py
      jobs/
        import_job.py
        metrics_job.py
        embedding_job.py
      tests/
        conftest.py
        test_ingestion/
        test_metrics/
        test_guardrails/
        test_isolation/    # Testes críticos de isolamento entre atletas
        test_api/
    alembic/
      env.py
      versions/
    pyproject.toml
    Dockerfile
    .env.example
  frontend/
    (Streamlit ou Next.js — a definir)
  docs/
    architecture.md
    api_integrations.md
    data_model.md
    training_methodology.md
    safety_rules.md
    validation_plan.md   # Plano de validação com os 2 atletas
  docker-compose.yml
  docker-compose.dev.yml
  README.md
  .env.example
  Makefile              # Comandos úteis: make up, make migrate, make test, make import

═══════════════════════════════════════════════════
FASES DO PROJETO
═══════════════════════════════════════════════════

FASE 0 — VALIDAÇÃO COM 2 ATLETAS (objetivo imediato)
  Prazo: antes de qualquer decisão comercial
  Entregáveis:
  - Sistema rodando localmente com docker-compose up
  - Suporte a 2 atletas com isolamento total de dados
  - Importação de dados históricos do TrainingPeaks via CSV
  - Importação de arquivos FIT de treinos
  - Cálculo correto de CTL/ATL/TSB
  - Primeira recomendação de treino gerada e explicada
  - Interface mínima para o atleta ver recomendações e dar feedback
  - Mecanismo de coleta de feedback funcionando
  - Admin consegue ver feedbacks dos 2 atletas
  Critério de saída: os 2 atletas usam por 4 semanas e dão feedback positivo

FASE 1 — FUNDAÇÃO
  Estrutura do projeto, Docker, FastAPI, PostgreSQL, modelos principais, CRUD básico, upload de arquivos, autenticação JWT, multi-tenant

FASE 2 — INGESTÃO HISTÓRICA
  Importação CSV, FIT, TCX, GPX, normalização, validação de qualidade, deduplicação, jobs assíncronos

FASE 3 — MÉTRICAS E ANÁLISE
  CTL, ATL, TSB, TSS, IF, NP, curva de potência, evolução de FTP, análise por blocos

FASE 4 — PROVAS E PERIODIZAÇÃO
  Cadastro de provas, blocos de treinamento, base/build/peak/taper/recovery, relatórios pré e pós-prova

FASE 5 — IA E RAG
  Base de conhecimento, embeddings, consulta ao histórico, recomendações com guardrails, explicabilidade, evidências, registro de decisões

FASE 6 — INTEGRAÇÕES EXTERNAS
  Strava OAuth (prioridade 1), Garmin (prioridade 2), TrainingPeaks API (se disponível), Intervals.icu, conectores manuais para o restante

FASE 7 — DASHBOARD
  Calendário, gráfico de carga, forma, fadiga, recomendações, provas, alertas, relatórios de evolução

FASE 8 — EVOLUÇÃO AVANÇADA
  Digital Twin completo, modelos preditivos, comparação de blocos, detecção de padrões, recomendações adaptativas, feedback loop de aprendizado

═══════════════════════════════════════════════════
SAÍDAS ESPERADAS
═══════════════════════════════════════════════════

PARTE 1 — ARQUITETURA E DOCUMENTAÇÃO
  1. Visão geral da arquitetura com diagrama em texto (ASCII ou Mermaid).
  2. Matriz de APIs e integrações com estratégia de integração por prioridade.
  3. Modelo de dados detalhado com relacionamentos.
  4. Estratégia de ingestão e normalização de dados.
  5. Estratégia de IA e RAG.
  6. Guardrails de segurança com algoritmo de validação.
  7. Plano de implementação por fases com critérios de saída de cada fase.
  8. Estrutura de pastas completa.
  9. Schema SQL inicial comentado.
  10. Plano de validação com os 2 atletas (o que medir, como coletar feedback, critérios de sucesso).

PARTE 2 — CÓDIGO INICIAL
  Implemente o esqueleto funcional com:
  - FastAPI rodando com health check.
  - PostgreSQL + pgvector no docker-compose.
  - SQLAlchemy async configurado.
  - Alembic configurado com primeira migração.
  - Autenticação JWT funcionando.
  - Isolamento de tenant implementado e testado.
  - Modelos principais com soft delete.
  - Schemas Pydantic v2.
  - Rotas básicas de CRUD de atleta e treino.
  - Upload e importação de CSV e FIT.
  - Cálculo de TSS, CTL, ATL, TSB.
  - Estrutura de guardrails implementada (mesmo que incompleta).
  - Endpoint de recomendação com placeholder de LLM.
  - Endpoint de feedback de recomendação.
  - Testes de ingestão, cálculo e isolamento.
  - README com instruções para rodar em 3 comandos.
  - Makefile com comandos úteis.
  - .env.example completo.

═══════════════════════════════════════════════════
REGRAS DE IMPLEMENTAÇÃO
═══════════════════════════════════════════════════

- Não gerar código comentado ou TODOs sem implementação correspondente.
- Não usar dados de exemplo hard-coded em produção.
- Não misturar dados reais com dados inferidos em nenhuma tabela.
- Não aumentar carga sugerida agressivamente — máximo 10% por semana.
- Não ignorar fadiga, sono ou HRV nas recomendações.
- Não chamar LLM sem validar guardrails primeiro.
- Registrar todas as decisões da IA no banco com timestamp.
- Toda recomendação deve ter evidências rastreáveis no histórico real do atleta.
- Toda recomendação pode ser rejeitada ou ajustada pelo atleta.
- Nenhuma query retorna dados cruzados entre tenants.
- Soft delete em todos os registros — nunca DELETE físico.
- Logs estruturados em JSON em todos os serviços.
- Variáveis sensíveis apenas em .env, nunca hard-coded.
- Código em inglês, documentação de usuário em português.

COMECE AGORA.

Entregue primeiro a arquitetura completa documentada. Em seguida, gere todos os arquivos de código. Não pare no meio — complete cada seção antes de passar para a próxima. Se precisar tomar decisões de design, tome e justifique. Não peça confirmação para decisões técnicas de implementação padrão.
```
