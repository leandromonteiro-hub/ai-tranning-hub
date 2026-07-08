# Legibilidade da recomendação (render markdown + traduções)

**Data:** 2026-07-08 · **Status:** aprovado
**Contexto:** o campo "Racional" da recomendação mostra o texto do LLM em
markdown **cru** — `##`, `**`, `-` aparecem literais e as quebras somem,
virando um paredão ilegível — porque o componente `Field` renderiza `value`
como texto puro. Além disso, três campos aparecem em **inglês** (defaults fixos
no backend). Esta spec renderiza o markdown e traduz os defaults.

## Decisões (aprovadas pelo usuário)

- **Renderizar o markdown** do Racional + **traduzir os 3 textos** em inglês.
  NÃO mexer no que a IA escreve (sem mudança de prompt/template).
- **Renderizador próprio e leve** (sem dependência nova tipo react-markdown):
  o texto da IA é um subconjunto previsível de markdown; peça pura e testável,
  estilo Tailwind + dark mode sob controle total. Degrada mostrando a linha
  crua se algo fugir do subconjunto — nunca quebra.

## Arquitetura

### Frontend

- `web/lib/markdown.tsx` — função pura `renderMarkdown(text: string): ReactNode`
  que parseia o subconjunto de markdown que o LLM emite e devolve JSX estilizado:
  - `#`/`##`/`###` → cabeçalhos (tamanhos/peso decrescentes, cor de título).
  - `**negrito**` (inline) → `<strong>`.
  - linhas iniciadas por `- ` ou `* ` → itens de lista (`<ul><li>`).
  - `---` sozinho na linha → separador (espaçamento/`<hr>`).
  - linhas em branco separam parágrafos; linhas de texto viram `<p>`.
  - texto sem markdown passa como parágrafo simples.
  - dark mode: classes `dark:` coerentes com o resto do app.
- `web/components/recs/RecsSections.tsx` (`RationalePanel`): o campo **Racional**
  passa a renderizar `renderMarkdown(rec.rationale)` num container próprio (não
  mais via `Field`, que continua para os campos curtos). Objetivo, Relação,
  "Se mais cansado", "Se menos tempo" permanecem como `Field` (frases de 1
  linha), agora em pt-BR (vindo do backend).

### Backend

- `backend/app/services/ai/recommender.py`: traduzir os 3 defaults para pt-BR:
  - `_objective(...)` retorno: "Targeted stimulus aligned with the current
    training block and recent load." → "Estímulo direcionado ao bloco de treino
    atual e à carga recente."
  - `adjust_if_tired`: "If more fatigued than the snapshot indicates, drop to
    Z1-Z2 endurance or take full rest; never push intensity on a high-fatigue
    day." → "Se estiver mais cansado do que os números indicam, caia para
    endurance Z1–Z2 ou descanse por completo; nunca force intensidade em dia de
    fadiga alta."
  - `adjust_if_less_time`: "If less time is available, keep the primary
    intensity interval(s) and trim warm-up/cool-down and endurance volume." →
    "Se tiver menos tempo, mantenha o(s) intervalo(s) principal(is) de
    intensidade e corte aquecimento/volta à calma e o volume de endurance."

## Escopo / não-objetivos

- Não alterar o prompt/template nem o conteúdo que a IA gera (o Racional segue
  vindo do LLM; só a APRESENTAÇÃO muda).
- Não adicionar dependência de markdown (renderizador próprio).
- Não tocar no `SignalsPanel`/cards de treino — só o Racional e os 3 defaults.
- Recomendações antigas (rationale já em markdown) renderizam igual — a
  mudança é só de exibição, sem migração.

## Testes

**Web (vitest):**
- `web/lib/__tests__/markdown.test.tsx`: `##` vira cabeçalho (não texto literal);
  `**x**` vira `<strong>`; linhas `- ` viram itens de lista; parágrafos
  separados por linha em branco; texto puro sem markdown vira um parágrafo;
  `---` não aparece como texto literal.
- `web/components/recs/__tests__/RationalePanel.test.tsx` (novo OU ajuste):
  dado um `rec.rationale` com `## Título` e `**negrito**`, o DOM contém um
  heading e um `<strong>`, e NÃO contém a string literal `##`/`**`.

**Backend (pytest):**
- ajustar qualquer teste que fixasse as strings em inglês dos 3 defaults; se
  houver assert do `physiological_objective`/`adjust_*`, atualizar para o texto
  pt-BR. Se nenhum teste fixa, nenhuma mudança de teste é necessária além de
  confirmar a suíte verde.
