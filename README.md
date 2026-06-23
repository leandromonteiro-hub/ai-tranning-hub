# 🚴 Athlete AI Training Hub

Sistema modular de gestão de treinamento de ciclismo/MTB orientado por IA. Consolida
dados esportivos, fisiológicos, competitivos e subjetivos do atleta em um repositório
central (Athlete Data Hub), mantém um **Gêmeo Digital** do atleta e gera **recomendações
explicáveis e rastreáveis** com validação de segurança (guardrails) antes de qualquer
chamada ao LLM.

> **Aviso:** ferramenta de apoio à análise e decisão. **Não substitui** avaliação médica
> ou profissional. Toda recomendação pode ser rejeitada ou ajustada pelo atleta.

Esta é a **Fase 0 — validação com 2 atletas**. Prioridade: funcionar muito bem para 2
pessoas, com isolamento total de dados, antes de qualquer decisão comercial.

---

## ▶️ Rodar em 3 comandos

```bash
cp .env.example .env          # 1. configurar ambiente
docker compose up -d --build  # 2. subir api + worker + postgres(pgvector) + redis + frontend
docker compose exec api python -m app.scripts.seed   # 3. criar admin + 2 atletas de teste
```

Popule a base de conhecimento (necessária para o RAG das recomendações) e,
opcionalmente, gere dados de demonstração:

```bash
docker compose exec api python -m app.scripts.seed_knowledge   # base de conhecimento (RAG)
docker compose exec api python -m app.scripts.sample_import     # dados de demo (opcional)
```

Acesse:
- **API + Swagger:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health
- **Frontend (Streamlit):** http://localhost:8501

Contas criadas pelo seed:

| Papel    | Email                              | Senha          |
|----------|------------------------------------|----------------|
| ADMIN    | `admin@athletehub.example.com`     | `admin_dev_pwd`|
| ATHLETE  | `athlete1@athletehub.example.com`  | `athlete1_pwd` |
| ATHLETE  | `athlete2@athletehub.example.com`  | `athlete2_pwd` |

> Troque todas as senhas e o `JWT_SECRET_KEY` antes de qualquer uso real.

---

## 🧱 Arquitetura (resumo)

```
FIT/TCX/GPX/CSV ─▶ Ingestão ─▶ PostgreSQL 16 + pgvector ◀─ Métricas (CTL/ATL/TSB, TSS…)
                                      ▲                         │
        Streamlit ◀─ FastAPI (JWT, multi-tenant, audit) ◀──────┘
                          │
                          ▼
        Training Intelligence Layer:
        Digital Twin ─▶ Guardrails (SEMPRE antes do LLM) ─▶ Evidências (RAG) ─▶ LLM logado
```

Detalhes completos em [`docs/architecture.md`](docs/architecture.md).

### Decisões técnicas principais
- **Streamlit** (não Next.js) para o MVP: feedback loop funcional em um só código Python.
- **RAG próprio** sobre pgvector (sem LangChain): controle total de versionamento de prompt,
  rastreabilidade de evidências e log de chamadas ao LLM.
- **PostgreSQL puro + pgvector** (sem TimescaleDB no MVP): volume de 2 atletas não justifica
  a complexidade; caminho de migração documentado.
- **Cliente LLM abstraído** (Anthropic `claude-opus-4-8` por padrão), com provider `mock`
  para rodar tudo offline, sem chave de API.

---

## 🔒 Isolamento multi-tenant

Cada atleta tem `tenant_id` único e todos os dados carregam `athlete_id`. O isolamento é
imposto na **camada de repositório** (`app/repositories/base.py`): toda query adiciona
`athlete_id == contexto` e `deleted_at IS NULL`. Nenhuma rota consegue cruzar tenants;
apenas ADMIN, de forma explícita e auditada. Coberto por
`app/tests/test_isolation/` e por testes de API.

---

## 🧪 Testes

```bash
docker compose exec api pytest -q          # tudo
docker compose exec api pytest --cov=app   # com cobertura
```

Suítes: ingestão (CSV/FIT), cálculo de métricas (TSS/IF/NP/CTL/ATL/TSB), guardrails de
segurança, **isolamento entre atletas**, e API ponta a ponta. Rodam em SQLite em memória,
sem necessidade de Postgres.

---

## 📚 Documentação

| Documento | Conteúdo |
|-----------|----------|
| [`docs/architecture.md`](docs/architecture.md)         | Visão geral, diagramas, fluxos, topologia |
| [`docs/data_model.md`](docs/data_model.md)             | Modelo de dados e relacionamentos |
| [`docs/api_integrations.md`](docs/api_integrations.md) | Matriz de APIs (Strava, Garmin, Oura…) e estratégia |
| [`docs/training_methodology.md`](docs/training_methodology.md) | Base conceitual de treinamento |
| [`docs/safety_rules.md`](docs/safety_rules.md)         | Algoritmo de guardrails de segurança |
| [`docs/validation_plan.md`](docs/validation_plan.md)   | Plano de validação com os 2 atletas |
| [`docs/schema.sql`](docs/schema.sql)                   | Schema SQL inicial comentado |

---

## 🗂️ Estrutura

```
backend/   FastAPI + SQLAlchemy async + Alembic + Celery (app/, alembic/, tests/)
frontend/  Streamlit (validação)
docs/      arquitetura, modelo de dados, integrações, metodologia, segurança, validação
docker-compose.yml / .dev.yml   stack local completa
Makefile   make up | dev | migrate | seed | import | test
```

## 🛠️ Comandos úteis (Makefile)

`make up` · `make dev` · `make migrate` · `make seed` · `make import` · `make test` ·
`make logs` · `make shell-db`

---

## 🔌 Integrações (roadmap)

1. Upload manual FIT/CSV + export TrainingPeaks (já no MVP)
2. Strava OAuth
3. Intervals.icu
4. Oura / Whoop (recuperação)
5. Garmin / TrainingPeaks API (via parceria, depois)

Detalhes e matriz comparativa em [`docs/api_integrations.md`](docs/api_integrations.md).
