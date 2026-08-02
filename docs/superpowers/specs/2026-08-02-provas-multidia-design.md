# Provas de múltiplos dias (stage races XCM) — design

Data: 2026-08-02 · Status: aprovado pelo Leandro (chat)

## Problema

O calendário de provas só aceita provas de um dia (`races.race_date`). Ultramaratonas
e stage races de XCM ocupam 2-3 dias **consecutivos** — hoje o atleta teria que
cadastrar cada dia como prova separada, e a IA recomendaria treino no dia 2 de
uma prova em andamento.

## Decisões de escopo (conversadas)

- **Período + totais, sem etapas.** A prova ganha início e fim; distância e
  altimetria seguem sendo totais da prova. Detalhe por etapa ficou de fora
  (YAGNI) — se fizer falta, é outra feature.
- **Taper mira o dia 1; a prova bloqueia os dias.** Plano e taper continuam
  apontando para `race_date` (primeiro dia). Todos os dias do período contam
  como dia de prova: marcador no calendário e nenhum treino prescrito dentro
  do período. `days_until` conta para o dia 1.
- **Resultado continua um por prova** (não por dia) — coerente com "período +
  totais".

## Modelo de dados

`races` ganha `end_date: Date | None` (nullable, sem default).

- `NULL` ⇒ prova de 1 dia. **Todas as provas existentes continuam válidas sem
  migração de dados.**
- Convenção de leitura em TODOS os consumidores:
  `ultimo_dia = end_date ?? race_date`; um dia `d` é dia de prova se
  `race_date <= d <= ultimo_dia`.
- Por que `end_date` e não `duration_days`: as leituras (calendário, plano)
  perguntam "este dia cai no período?" — com `end_date` isso é um `BETWEEN`;
  com duração seria aritmética de datas em cada consulta. O custo de escrita é
  igual.

Migração `0013_race_end_date` seguindo o padrão do PR #23
(`add_column_if_missing` / `drop_column_if_exists` de
`app/db/migration_utils.py`).

## API (backend)

- `RaceCreate` / `RaceUpdate` / `RaceRead` (schemas/race.py): campo opcional
  `end_date: date | None = None`.
- Validação no schema (Pydantic, não no banco): `end_date >= race_date` e
  `end_date - race_date <= 13` (prova de no máx. 14 dias — guarda contra typo
  de ano). Violações ⇒ 422.
- `RaceMarker` (schemas/calendar.py) ganha `end_date` também, para o front
  desenhar a faixa.

## Comportamento (calendário, plano, IA)

- **calendar.py**: o filtro de provas futuras e a montagem de `RaceMarker`
  passam a usar `ultimo_dia`. O marcador aparece em cada dia do período;
  `days_until` segue relativo a `race_date` (negativo durante a prova é
  aceitável e informativo — "dia 2 de 3").
- **Recomendação/plano**: nenhum treino prescrito em dia que caia dentro do
  período de uma prova. O ponto de corte de geração de plano
  (`plan_service.py` / `plan_expander.py`) continua `race_date` — já não
  prescreve depois da prova-alvo; a mudança relevante é o plano não cair em
  dias de provas intermediárias (B/C) de múltiplos dias.
- **Taper do twin (`methodology.py`)**: sem mudança — janela continua
  `[race_date - 21d, race_date]`.
- **Contexto da IA**: onde a prova é descrita para o LLM, incluir o período
  quando houver (`12–14/09`, "prova de 3 dias") para o racional falar a coisa
  certa.

## UI (web, página Provas)

- Formulário: campo **"Dias"** (número inteiro, padrão 1, mín. 1, máx. 14) ao
  lado da data. O front converte para `end_date = race_date + (dias - 1)` ao
  enviar; não expõe date-picker de fim.
- Tabela: coluna de data mostra o período quando `end_date` existir —
  `12/09/2026 – 14/09/2026` (ou compacto `12–14/09/2026`); um dia mostra como
  hoje.
- Calendário da visão geral: a faixa/badge da prova aparece em todos os dias
  do período (vem de `RaceMarker.end_date`).

## Testes

- **Schema (backend)**: `end_date` < `race_date` ⇒ 422; período > 14 dias ⇒
  422; ausente ⇒ ok (1 dia).
- **Calendário (backend)**: prova de 3 dias gera marcador nos 3 dias;
  `days_until` conta para o dia 1; nenhum treino prescrito nos dias 2-3.
- **Migração**: guarda estática do PR #23 já cobre (usar helpers).
- **UI (web)**: form envia `end_date` correto a partir de "Dias"; tabela
  renderiza período; prova de 1 dia continua igual.

## Fora de escopo

- Etapas com distância/altimetria próprias.
- Resultado por dia.
- Provas com dias NÃO consecutivos (não é o caso de uso).
