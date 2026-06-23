# Guia de operação — Validação com 2 atletas (Fase 0)

Como rodar a validação de 4 semanas. O sistema está completo de ponta a ponta com IA real:
importar histórico → métricas de carga → prova → plano periodizado → recomendação diária
ciente da fase → treino estruturado exportável (.fit/.zwo) → feedback do atleta → painel do
treinador.

---

## 0. Pré-requisito de segurança (faça primeiro)

A chave da API Anthropic foi exposta uma vez durante o desenvolvimento. **Revogue-a e gere uma
nova** antes de iniciar a validação:

1. https://console.anthropic.com → Settings → API keys → revogar a chave atual.
2. Criar nova chave (`sk-ant-...`).
3. Editar `C:\projetos\treinador-ciclismo\.env`: `ANTHROPIC_API_KEY=<nova chave>`.
4. `docker compose up -d` (reinicia para reler o `.env`).

---

## 1. Subir o sistema

Do diretório `C:\projetos\treinador-ciclismo` (Git Bash):

```bash
docker compose up -d --build                                   # api + worker + postgres + redis + frontend
docker compose exec api alembic upgrade head                   # garante o schema (roda no start, mas confirme)
docker compose exec api python -m app.scripts.seed             # admin + 2 atletas + FTP
docker compose exec api python -m app.scripts.seed_knowledge   # base de conhecimento (RAG) — baixa o modelo de embeddings na 1ª vez
```

Acessos:
- **Frontend (atletas + treinador):** http://localhost:8501
- **API + Swagger:** http://localhost:8000/docs

Contas (troque as senhas para uso real):

| Papel    | Email                              | Senha           |
|----------|------------------------------------|-----------------|
| ADMIN    | `admin@athletehub.example.com`     | `admin_dev_pwd` |
| ATLETA 1 | `athlete1@athletehub.example.com`  | `athlete1_pwd`  |
| ATLETA 2 | `athlete2@athletehub.example.com`  | `athlete2_pwd`  |

> **Ativação da IA real** (já configurada no `.env`): `LLM_PROVIDER=anthropic` (`claude-opus-4-8`,
> ~$0.03/recomendação) e `EMBEDDING_PROVIDER=local` (fastembed, offline, sem custo).

---

## 2. Fluxo do ATLETA (no frontend, logado como atleta)

1. **📥 Importar** — subir o histórico real (CSV export do TrainingPeaks, ou arquivos FIT/TCX/GPX).
2. **📈 Forma & Carga** — conferir CTL/ATL/TSB; botão "Recalcular métricas" se necessário.
3. **🏁 Provas** — cadastrar a prova-alvo (nome, data futura, prioridade A/B/C).
4. **📅 Plano** — selecionar a prova → "Gerar plano" → ver o calendário (base→build→peak→taper).
5. **🧠 Recomendações** — ver a fase do dia, gerar a recomendação (IA real, com guardrails e
   evidências do histórico), **baixar o treino**:
   - **.zwo** → importar no TrainingPeaks (Workout Library → menu 3 pontos → Workout Import).
   - **.fit** → device via USB (pasta `Garmin/NewFiles/` do ciclocomputador).
6. Após executar o treino, **dar feedback** (nota 1–5, "fez sentido", comentário).

> ⚠️ Treino estruturado é **baseado em potência (%FTP)**. As recomendações só ficam específicas
> da fase quando há um plano cobrindo o dia (senão usam o bloco padrão BASE).

---

## 3. Fluxo do TREINADOR (logado como `admin@...`)

O **📋 Painel do treinador** mostra:
- **Métricas da validação:** nº de atletas, treinos, recomendações, feedbacks e **nota média**.
- **Atletas:** lista dos 2 atletas.
- **Feedbacks:** por data, **atribuídos a cada atleta** (nota, "fez sentido", comentário).

Acompanhe semanalmente: volume de uso (recomendações geradas), e a qualidade percebida
(nota média + comentários). Critério de saída da Fase 0: os 2 atletas usam por 4 semanas e dão
feedback positivo.

---

## 4. O que observar nas 4 semanas

- As recomendações fazem sentido para o atleta? (nota e "fez sentido")
- O atleta consegue executar o treino exportado no device/TrainingPeaks sem fricção?
- Os guardrails estão protegendo (ex.: TSB muito negativo → recomendação conservadora)?
- Custo de IA acumulado (Swagger/logs `llm_call_logs`) — esperado: centavos por recomendação.

---

## 5. Limitações conhecidas (aceitas nesta fase)

- **Import no device é manual** (.fit USB / .zwo no TP). Não há sync automático com
  Strava/Garmin (Fase 6, adiada por decisão).
- **Gate manual pendente:** confirmar que um `.fit` real importa e executa no Garmin de um dos
  atletas (atenção: repetições são achatadas — um 3×12 aparece como 6 passos sequenciais).
- Treino estruturado e `.zwo` são **potência/%FTP**; sem alvos por FC ainda.

---

## 6. Testes e manutenção

```bash
# Suíte de testes (SQLite, offline) — 73 testes
docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' && python -m pytest -q"

docker compose logs -f api        # logs da API
docker compose down               # parar tudo (mantém dados)
docker compose down -v            # parar e APAGAR os dados (volume pgdata)
```

> Nota local: `docker-compose.override.yml` remapeia as portas de host (Postgres 5433, Redis
> 6380) para conviver com outra stack na mesma máquina; a comunicação entre containers usa as
> portas internas normais.
