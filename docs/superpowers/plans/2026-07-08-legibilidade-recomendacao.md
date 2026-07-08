# Legibilidade da recomendação Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Renderizar o markdown do campo "Racional" (hoje um paredão de texto cru) como documento formatado, e traduzir os textos-default que estão em inglês.

**Architecture:** Um renderizador de markdown próprio e leve (função pura, sem dependência nova) parseia o subconjunto que o LLM emite (títulos, negrito, listas, parágrafos, separador) em JSX estilizado; o `RationalePanel` passa a usá-lo no Racional. No backend, 4 strings-default em inglês viram pt-BR.

**Tech Stack:** Next.js 15 + React 19 + Tailwind; vitest + @testing-library/react (react plugin + jsdom já configurados). Backend: FastAPI (só troca de literais).

**Spec:** `docs/superpowers/specs/2026-07-08-legibilidade-recomendacao-design.md`

## Global Constraints

- pt-BR; sem dependência nova de markdown (renderizador próprio); não mexer no prompt/conteúdo da IA.
- Testes web no host: `cd web && npx vitest run <PATH>`. Backend via Docker.
- Branch: `feat/legibilidade-recomendacao` (já existe, spec commitada).
- Commits terminam com `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Subconjunto de markdown suportado (verbatim): `#`/`##`/`###` títulos, `**negrito**` inline, linhas `- `/`* ` como itens de lista, `---`/`***` separador, linha em branco separa parágrafos; o resto é parágrafo simples (degrada mostrando a linha, nunca quebra).

---

### Task 1: renderMarkdown + RationalePanel

**Files:**
- Create: `web/lib/markdown.tsx`
- Modify: `web/components/recs/RecsSections.tsx` (`RationalePanel`)
- Test: `web/lib/__tests__/markdown.test.tsx`
- Test: `web/components/recs/__tests__/RationalePanel.test.tsx`

**Interfaces:**
- Consumes: nada novo.
- Produces: `renderMarkdown(text: string | null): ReactNode` (retorna `null` p/ vazio; senão um `<div class="space-y-2">` com blocos). `RationalePanel` renderiza o Racional via `renderMarkdown(rec.rationale)`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `web/lib/__tests__/markdown.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '@/lib/markdown'

function show(md: string) {
  return render(<div data-testid="md">{renderMarkdown(md)}</div>)
}

describe('renderMarkdown', () => {
  it('título ## vira heading, não texto literal', () => {
    show('## Objetivo fisiológico')
    expect(screen.getByText('Objetivo fisiológico')).toBeInTheDocument()
    expect(screen.getByTestId('md').textContent).not.toContain('##')
  })

  it('**negrito** vira <strong>', () => {
    show('Isto é **importante** aqui')
    const strong = screen.getByText('importante')
    expect(strong.tagName).toBe('STRONG')
    expect(screen.getByTestId('md').textContent).not.toContain('**')
  })

  it('linhas "- " viram itens de lista', () => {
    show('- primeiro\n- segundo')
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('primeiro')
  })

  it('texto puro sem markdown vira um parágrafo', () => {
    show('Apenas um texto simples.')
    expect(screen.getByText('Apenas um texto simples.').tagName).toBe('P')
  })

  it('--- não aparece como texto literal', () => {
    show('Antes\n---\nDepois')
    expect(screen.getByTestId('md').textContent).not.toContain('---')
  })

  it('vazio/null retorna nada', () => {
    const { container } = render(<div>{renderMarkdown(null)}</div>)
    expect(container.querySelector('div')?.textContent).toBe('')
  })
})
```

Criar `web/components/recs/__tests__/RationalePanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RationalePanel } from '@/components/recs/RecsSections'
import type { Recommendation } from '@/lib/types'

function rec(rationale: string): Recommendation {
  return {
    id: 'r', target_date: null, kind: 'daily_workout', summary: 's',
    physiological_objective: 'Estímulo direcionado', block_relation: 'Bloco BASE',
    rationale, adjust_if_tired: 'Se cansado…', adjust_if_less_time: 'Se menos tempo…',
    payload: null, risk_level: 'LOW', risk_flags: null, confidence: 0.7,
    confidence_rationale: null, decision: 'PENDING', created_at: '2026-07-08T00:00:00Z',
    evidence: [],
  } as Recommendation
}

describe('RationalePanel', () => {
  it('renderiza o Racional em markdown (heading + strong, sem sintaxe crua)', () => {
    render(<RationalePanel rec={rec('## Sessão\nFaça **Z2** hoje')} />)
    expect(screen.getByText('Sessão')).toBeInTheDocument()
    expect(screen.getByText('Z2').tagName).toBe('STRONG')
    // o container do racional não mostra os caracteres crus
    expect(document.body.textContent).not.toContain('## Sessão')
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run lib/__tests__/markdown.test.tsx components/recs/__tests__/RationalePanel.test.tsx`
Expected: FAIL — `@/lib/markdown` inexistente

- [ ] **Step 3: Implementar**

Criar `web/lib/markdown.tsx`:

```tsx
import { type ReactNode } from 'react'

/** Parseia negrito inline (**texto**) numa lista de nós. */
function inline(text: string, keyBase: string): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .filter((p) => p !== '')
    .map((p, i) => {
      if (p.length > 4 && p.startsWith('**') && p.endsWith('**')) {
        return <strong key={`${keyBase}-b${i}`}>{p.slice(2, -2)}</strong>
      }
      return <span key={`${keyBase}-t${i}`}>{p}</span>
    })
}

/** Renderiza o subconjunto de markdown que o LLM emite (títulos, negrito,
 *  listas, parágrafos, separador) como JSX estilizado (Tailwind + dark mode).
 *  Qualquer coisa fora do subconjunto degrada para parágrafo simples. */
export function renderMarkdown(text: string | null): ReactNode {
  if (!text || !text.trim()) return null
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let para: string[] = []
  let bullets: string[] = []
  let k = 0

  const flushPara = () => {
    if (para.length) {
      const key = `p${k++}`
      blocks.push(
        <p key={key} className="text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          {inline(para.join(' '), key)}
        </p>,
      )
      para = []
    }
  }
  const flushBullets = () => {
    if (bullets.length) {
      const key = `u${k++}`
      blocks.push(
        <ul key={key} className="list-disc space-y-1 pl-5 text-sm text-slate-600 dark:text-slate-300">
          {bullets.map((b, i) => <li key={`${key}-${i}`}>{inline(b, `${key}-${i}`)}</li>)}
        </ul>,
      )
      bullets = []
    }
  }

  for (const raw of lines) {
    const line = raw.trim()
    if (line === '') { flushPara(); flushBullets(); continue }
    if (line === '---' || line === '***') {
      flushPara(); flushBullets()
      blocks.push(<hr key={`h${k++}`} className="my-2 border-slate-200 dark:border-slate-700" />)
      continue
    }
    const h = /^(#{1,3})\s+(.*)$/.exec(line)
    if (h) {
      flushPara(); flushBullets()
      const level = h[1].length
      const key = `hd${k++}`
      const cls =
        level === 1
          ? 'mt-3 text-base font-bold text-slate-800 dark:text-slate-100'
          : level === 2
            ? 'mt-3 text-sm font-bold text-slate-800 dark:text-slate-100'
            : 'mt-2 text-sm font-semibold text-slate-700 dark:text-slate-200'
      blocks.push(<div key={key} className={cls}>{inline(h[2], key)}</div>)
      continue
    }
    const b = /^[-*]\s+(.*)$/.exec(line)
    if (b) { flushPara(); bullets.push(b[1]); continue }
    flushBullets()
    para.push(line)
  }
  flushPara(); flushBullets()
  return <div className="space-y-2">{blocks}</div>
}
```

Em `web/components/recs/RecsSections.tsx`:

1. Adicionar o import no topo: `import { renderMarkdown } from '@/lib/markdown'`.

2. No `RationalePanel`, trocar a linha do Racional
`<Field label="Racional" value={rec.rationale} />` por um bloco próprio:

```tsx
          {rec.rationale && (
            <div className="text-sm">
              <div className="mb-1 font-semibold text-slate-700 dark:text-slate-200">Racional</div>
              {renderMarkdown(rec.rationale)}
            </div>
          )}
```

(os demais `Field` — Objetivo, Relação, Se mais cansado, Se menos tempo — ficam iguais.)

- [ ] **Step 4: Rodar e ver passar (suíte web completa + tsc)**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: toda a suíte web verde; `tsc` sem erros

- [ ] **Step 5: Commit**

```bash
git add web/lib/markdown.tsx web/lib/__tests__/markdown.test.tsx web/components/recs/RecsSections.tsx web/components/recs/__tests__/RationalePanel.test.tsx
git commit -m "feat(web): renderiza o Racional em markdown (fim do paredão de texto cru)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Traduzir os defaults do backend

**Files:**
- Modify: `backend/app/services/ai/recommender.py` (`_objective` + 2 literais)

**Interfaces:**
- Consumes: nada.
- Produces: `physiological_objective`, `adjust_if_tired`, `adjust_if_less_time` em pt-BR.

- [ ] **Step 1: Escrever o teste que falha**

Adicionar ao final de `backend/app/tests/test_ai/test_comparative_payload.py` (reusa o mesmo setup/monkeypatch do arquivo):

```python
@pytest.mark.asyncio
async def test_default_texts_are_portuguese(session, two_athletes, monkeypatch):
    a, _ = two_athletes
    ctx = ctx_for(a)
    monkeypatch.setattr(
        "app.services.ai.recommender.FtpRepository.value_on",
        lambda self, d, aid: 250.0,
    )
    monkeypatch.setattr(
        "app.services.ai.recommender.TrainingWeekRepository.block_on",
        lambda self, d, aid: BlockType.BASE,
    )
    from app.models.athlete import AthleteProfile
    session.add(AthleteProfile(
        athlete_id=a.id, birth_date=date(1990, 1, 1), sex="M", weight_kg=70,
        height_cm=175, max_hr=185, primary_discipline="XCM", years_training=5,
        goals="ultra", weekly_hours=10,
    ))
    await session.flush()
    rec = await generate_recommendation(session, ctx, a.id, target_date=date(2026, 7, 7))
    # Sem palavras em inglês nos defaults; presença de acento/pt-BR.
    assert "stimulus" not in (rec.physiological_objective or "").lower()
    assert "if more fatigued" not in (rec.adjust_if_tired or "").lower()
    assert "if less time" not in (rec.adjust_if_less_time or "").lower()
    assert "Estímulo" in (rec.physiological_objective or "")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_ai/test_comparative_payload.py::test_default_texts_are_portuguese -q --no-header -p no:warnings"`
Expected: FAIL — os textos ainda estão em inglês

- [ ] **Step 3: Implementar**

Em `backend/app/services/ai/recommender.py`:

1. `_objective` (ambas as strings):

```python
def _objective(safety) -> str:
    if safety.risk_level == RiskLevel.HIGH:
        return "Recuperação / redução de carga para restaurar a prontidão antes de retomar o volume."
    return "Estímulo direcionado ao bloco de treino atual e à carga recente."
```

2. Os dois literais no `AiRecommendation(...)`:

```python
        adjust_if_tired="Se estiver mais cansado do que os números indicam, caia "
        "para endurance Z1–Z2 ou descanse por completo; nunca force intensidade "
        "em dia de fadiga alta.",
        adjust_if_less_time="Se tiver menos tempo, mantenha o(s) intervalo(s) "
        "principal(is) de intensidade e corte aquecimento/volta à calma e o volume "
        "de endurance.",
```

- [ ] **Step 4: Rodar e ver passar (+ regressão test_ai)**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_ai -q --no-header -p no:warnings; ruff check app/services/ai/recommender.py"`
Expected: verde + `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/recommender.py backend/app/tests/test_ai/test_comparative_payload.py
git commit -m "feat(recs): textos-default da recomendação em pt-BR (objetivo, ajustes)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
