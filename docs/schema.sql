-- ============================================================================
-- Athlete AI Training Hub — schema SQL inicial (comentado)
-- ----------------------------------------------------------------------------
-- Referência legível do modelo de dados. O schema REAL é criado/migrado pelos
-- modelos SQLAlchemy via Alembic (backend/alembic). Este arquivo documenta a
-- intenção e as convenções; mantenha-o em sincronia com os modelos.
--
-- Convenções (em TODAS as tabelas):
--   id          UUID  PRIMARY KEY
--   created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
--   updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
--   deleted_at  TIMESTAMPTZ NULL              -- soft delete (NUNCA DELETE físico)
--   created_by  UUID NULL                     -- quem criou o registro
--   athlete_id  UUID  -> athletes(id)         -- chave de tenant (quando aplicável)
--
-- Isolamento: toda query em tabela com athlete_id filtra por athlete_id do
-- contexto autenticado + deleted_at IS NULL (imposto na camada de repositório).
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector, para a tabela embeddings

-- ──────────────────────────── ATLETA E PERFIL ──────────────────────────────

-- Principal do sistema; define o tenant. NÃO tem athlete_id (ela É o atleta).
CREATE TABLE athletes (
    id              UUID PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,         -- bcrypt
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(16)  NOT NULL DEFAULT 'ATHLETE',  -- ADMIN|ATHLETE|COACH
    tenant_id       VARCHAR(64)  UNIQUE NOT NULL,  -- isolamento explícito
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- Perfil fisiológico/esportivo (1:1 com o atleta).
CREATE TABLE athlete_profiles (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    birth_date DATE, sex VARCHAR(16), height_cm DOUBLE PRECISION,
    weight_kg DOUBLE PRECISION, max_hr INT, resting_hr INT,
    primary_discipline VARCHAR(32),    -- XCO|XCM|gran_fondo|road|...
    years_training INT, notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- Objetivos de curto/médio/longo prazo com status e progresso.
CREATE TABLE athlete_goals (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    title VARCHAR(255) NOT NULL, horizon VARCHAR(16) DEFAULT 'medium',
    target_date DATE, status VARCHAR(16) DEFAULT 'ACTIVE', progress_pct DOUBLE PRECISION DEFAULT 0,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- Disponibilidade semanal recorrente e restrições de agenda.
CREATE TABLE athlete_availability (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    day_of_week INT NOT NULL,          -- 0=segunda .. 6=domingo
    available_minutes INT DEFAULT 0, constraints JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- ───────────────────────── FONTES E IMPORTAÇÃO ─────────────────────────────

-- Arquivos importados; content_hash = chave primária de deduplicação.
CREATE TABLE imported_files (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    filename VARCHAR(512) NOT NULL, file_format VARCHAR(8) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,           -- SHA-256 dos bytes
    size_bytes INT DEFAULT 0,
    status VARCHAR(16) DEFAULT 'PENDING',        -- PENDING|PROCESSING|COMPLETED|FAILED|DUPLICATE
    source VARCHAR(64), error_message TEXT, rows_imported INT DEFAULT 0, meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);
CREATE INDEX ix_imported_files_hash ON imported_files(content_hash);

-- ─────────────────────────────── TREINOS ──────────────────────────────────

-- Treinos EXECUTADOS (história real do atleta) com métricas derivadas.
CREATE TABLE workouts_completed (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    started_at TIMESTAMPTZ NOT NULL, workout_date DATE NOT NULL,
    name VARCHAR(255), workout_type VARCHAR(16) DEFAULT 'OTHER', sport VARCHAR(32) DEFAULT 'cycling',
    duration_s INT, distance_m DOUBLE PRECISION, elevation_gain_m DOUBLE PRECISION,
    avg_power DOUBLE PRECISION, normalized_power DOUBLE PRECISION,
    avg_hr DOUBLE PRECISION, max_hr DOUBLE PRECISION, avg_cadence DOUBLE PRECISION,
    kj DOUBLE PRECISION,
    intensity_factor DOUBLE PRECISION, tss DOUBLE PRECISION, ftp_used DOUBLE PRECISION,
    source_file_id UUID REFERENCES imported_files(id),   -- proveniência (dado real)
    external_id VARCHAR(128), notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);
CREATE INDEX ix_workouts_completed_date ON workouts_completed(athlete_id, workout_date);

-- Streams brutos por segundo (arrays). Candidata a hypertable TimescaleDB no futuro.
CREATE TABLE workout_streams (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    workout_id UUID NOT NULL REFERENCES workouts_completed(id),
    sample_rate_hz DOUBLE PRECISION DEFAULT 1.0,
    time_s INT[], power DOUBLE PRECISION[], heart_rate DOUBLE PRECISION[],
    cadence DOUBLE PRECISION[], altitude DOUBLE PRECISION[], speed DOUBLE PRECISION[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- Intervalos detectados/definidos por treino.
CREATE TABLE workout_intervals (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    workout_id UUID NOT NULL REFERENCES workouts_completed(id),
    label VARCHAR(128), start_s INT NOT NULL, duration_s INT NOT NULL,
    avg_power DOUBLE PRECISION, avg_hr DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- Treinos PRESCRITOS (separados dos executados, relacionáveis via recomendação).
CREATE TABLE workouts_planned (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    planned_date DATE NOT NULL, name VARCHAR(255) NOT NULL,
    workout_type VARCHAR(16) DEFAULT 'ENDURANCE', planned_duration_s INT, planned_tss DOUBLE PRECISION,
    structure JSONB, description TEXT,
    source_recommendation_id UUID,        -- rastreabilidade até a recomendação da IA
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- ─────────────────────────── POTÊNCIA E ZONAS ─────────────────────────────

-- FTP histórico com intervalo de vigência (valid_to NULL = vigente).
CREATE TABLE ftp_history (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    ftp_watts DOUBLE PRECISION NOT NULL, valid_from DATE NOT NULL, valid_to DATE,
    method VARCHAR(64), source VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- Melhores esforços (curva de potência) por duração e período.
CREATE TABLE power_curve (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    duration_s INT NOT NULL, best_power DOUBLE PRECISION NOT NULL,
    achieved_on DATE, period_label VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);
-- (power_zones / heart_rate_zones derivam do FTP/max_hr vigente — ver zones_calculator.py)

-- ────────────────── MÉTRICAS FISIOLÓGICAS E RECUPERAÇÃO ────────────────────

CREATE TABLE body_metrics (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    metric_date DATE NOT NULL, weight_kg DOUBLE PRECISION,
    body_fat_pct DOUBLE PRECISION, bmi DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

CREATE TABLE recovery_metrics (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    metric_date DATE NOT NULL, hrv_ms DOUBLE PRECISION, resting_hr INT,
    sleep_hours DOUBLE PRECISION, sleep_score DOUBLE PRECISION, recovery_score DOUBLE PRECISION,
    source VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID,
    UNIQUE (athlete_id, metric_date)
);

CREATE TABLE subjective_metrics (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    metric_date DATE NOT NULL, rpe DOUBLE PRECISION, mood INT, fatigue INT,
    motivation INT, soreness INT, injury_flag BOOLEAN DEFAULT FALSE, comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID,
    UNIQUE (athlete_id, metric_date)
);

-- ───────────────────────────── CARGA E FORMA ──────────────────────────────

-- Série diária de carga/forma (1 linha por atleta por dia).
CREATE TABLE load_metrics (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    metric_date DATE NOT NULL,
    daily_tss DOUBLE PRECISION DEFAULT 0,
    ctl DOUBLE PRECISION DEFAULT 0,    -- chronic / fitness (42d)
    atl DOUBLE PRECISION DEFAULT 0,    -- acute / fatigue (7d)
    tsb DOUBLE PRECISION DEFAULT 0,    -- form (ctl_ontem - atl_ontem)
    monotony DOUBLE PRECISION, strain DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID,
    UNIQUE (athlete_id, metric_date)
);

-- ──────────────────────── PROVAS E COMPETIÇÕES ─────────────────────────────

CREATE TABLE races (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    name VARCHAR(255) NOT NULL, race_date DATE NOT NULL, discipline VARCHAR(32),
    priority VARCHAR(8) DEFAULT 'A',   -- A=alvo, B, C
    location VARCHAR(255), distance_km DOUBLE PRECISION, elevation_gain_m DOUBLE PRECISION, notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

CREATE TABLE race_results (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    race_id UUID REFERENCES races(id),
    overall_position INT, category_position INT, finish_time_s INT,
    avg_power DOUBLE PRECISION, normalized_power DOUBLE PRECISION, tss DOUBLE PRECISION,
    analysis TEXT,                     -- análise pré/pós escrita pelo atleta ou pela IA
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- ──────────────────────── IA E RECOMENDAÇÕES ───────────────────────────────
-- Espinha auditável: cada recomendação registra prompt versionado, modelo,
-- confiança, riscos e EVIDÊNCIAS reais — separadas dos dados brutos do atleta.

CREATE TABLE prompt_templates (
    id UUID PRIMARY KEY, name VARCHAR(128) NOT NULL, version INT DEFAULT 1,
    content_hash VARCHAR(64) NOT NULL, template TEXT NOT NULL, is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

CREATE TABLE llm_call_logs (
    id UUID PRIMARY KEY, provider VARCHAR(32), model VARCHAR(64),
    prompt TEXT, response TEXT, prompt_tokens INT DEFAULT 0, completion_tokens INT DEFAULT 0,
    latency_ms INT DEFAULT 0, estimated_cost_usd DOUBLE PRECISION DEFAULT 0,
    success BOOLEAN DEFAULT TRUE, error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

CREATE TABLE ai_recommendations (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    target_date DATE, kind VARCHAR(32) DEFAULT 'daily_workout', question TEXT,
    summary TEXT NOT NULL, physiological_objective TEXT, block_relation TEXT, rationale TEXT,
    adjust_if_tired TEXT, adjust_if_less_time TEXT, payload JSONB,
    risk_level VARCHAR(8) DEFAULT 'LOW',          -- LOW|MODERATE|HIGH (guardrails)
    risk_flags JSONB, confidence DOUBLE PRECISION, confidence_rationale TEXT,
    prompt_template_id UUID REFERENCES prompt_templates(id),
    llm_call_id UUID REFERENCES llm_call_logs(id),
    decision VARCHAR(16) DEFAULT 'PENDING',       -- PENDING|ACCEPTED|REJECTED|MODIFIED
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- Evidências reais (ponteiros rastreáveis para linhas do histórico).
CREATE TABLE ai_recommendation_evidence (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    recommendation_id UUID NOT NULL REFERENCES ai_recommendations(id),
    evidence_type VARCHAR(64), ref_table VARCHAR(64), ref_id UUID,
    description TEXT, similarity DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- Decisão do atleta (aceita/rejeita/modifica).
CREATE TABLE ai_decisions (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    recommendation_id UUID NOT NULL REFERENCES ai_recommendations(id),
    decision VARCHAR(16), modified_payload JSONB, comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- Feedback PÓS-execução (dado de primeira classe para a validação).
CREATE TABLE ai_recommendation_feedback (
    id UUID PRIMARY KEY, athlete_id UUID NOT NULL REFERENCES athletes(id),
    recommendation_id UUID NOT NULL REFERENCES ai_recommendations(id),
    rating INT NOT NULL,               -- 1..5
    made_sense BOOLEAN, observed_result TEXT, comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- ─────────────────────── BASE DE CONHECIMENTO (GLOBAL) ─────────────────────
-- NUNCA misturada com dados do atleta.

CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY, title VARCHAR(255) NOT NULL, category VARCHAR(64),
    content TEXT NOT NULL, source VARCHAR(255), meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- Embeddings: athlete_id NULL = conhecimento global; setado = privado do atleta.
-- A separação é imposta na consulta (RAG nunca cruza os dois domínios).
CREATE TABLE embeddings (
    id UUID PRIMARY KEY,
    athlete_id UUID REFERENCES athletes(id),     -- NULL => documento de conhecimento
    namespace VARCHAR(32) DEFAULT 'knowledge',   -- knowledge|workout|race|comment
    ref_table VARCHAR(64), ref_id UUID, chunk_text TEXT NOT NULL,
    embedding VECTOR(1536),                       -- pgvector (dim = EMBEDDING_DIM)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);
-- Índice ANN para busca semântica (criar quando houver volume):
-- CREATE INDEX ix_embeddings_vec ON embeddings USING ivfflat (embedding vector_cosine_ops);

-- ──────────────────────────────── SISTEMA ─────────────────────────────────

-- Log de auditoria imutável (append-only): quem, o quê, onde, IP, status.
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY, actor_athlete_id UUID, actor_role VARCHAR(16), tenant_id VARCHAR(64),
    method VARCHAR(8), endpoint VARCHAR(255), action VARCHAR(64) NOT NULL,
    target_athlete_id UUID, payload_summary JSONB, ip_address VARCHAR(64), status_code INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);

-- Configuração por ambiente.
CREATE TABLE system_config (
    id UUID PRIMARY KEY, key VARCHAR(128) UNIQUE NOT NULL, value JSONB, environment VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ, created_by UUID
);
