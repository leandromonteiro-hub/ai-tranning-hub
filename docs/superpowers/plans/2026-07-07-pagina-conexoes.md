# Página "Conexões" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar uma página **Conexões** dedicada (rota + item no menu) que hospeda o `GarminCard`, e removê-lo da página Importar.

**Architecture:** Puro frontend, zero backend. Uma nova rota fina renderiza `ConexoesView`, que compõe o `GarminCard` existente (sem modificá-lo) numa grade de cards de provedor. O Sidebar ganha o item "Conexões". Importar perde o card e ganha um link.

**Tech Stack:** Next.js 15 App Router, React 19, Tailwind, lucide-react, vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-07-07-pagina-conexoes-design.md`

## Global Constraints

- UI em **pt-BR**; reusar `GarminCard` SEM modificá-lo; zero backend.
- Testes web no host: `cd web && npx vitest run <PATH>`.
- Branch: `feat/pagina-conexoes` (já existe, spec commitada).
- Commits terminam com `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Item do nav (verbatim): `{ label: "Conexões", href: "/conexoes", icon: Plug }` (lucide-react `Plug`), logo após "Importar" em `NAV_ITEMS`.

---

### Task 1: Página Conexões + item no menu

**Files:**
- Create: `web/components/conexoes/ConexoesView.tsx`
- Create: `web/app/(app)/conexoes/page.tsx`
- Modify: `web/components/Sidebar.tsx` (import `Plug` + item no `NAV_ITEMS`)
- Test: `web/components/conexoes/__tests__/ConexoesView.test.tsx`
- Test: `web/components/__tests__/Sidebar.test.tsx`

**Interfaces:**
- Consumes: `GarminCard` de `@/components/importar/GarminCard`; `Card` não é necessário (o GarminCard já é um card).
- Produces: `ConexoesView()` (named export); rota `/conexoes`; `NAV_ITEMS` passa a conter o item "Conexões".

- [ ] **Step 1: Escrever os testes que falham**

Criar `web/components/conexoes/__tests__/ConexoesView.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ConexoesView } from '@/components/conexoes/ConexoesView'

vi.mock('@/components/importar/GarminCard', () => ({
  GarminCard: () => <div data-testid="garmin-card" />,
}))

describe('ConexoesView', () => {
  it('renderiza o título Conexões', () => {
    render(<ConexoesView />)
    expect(screen.getByText('Conexões')).toBeInTheDocument()
  })

  it('renderiza o card do Garmin', () => {
    render(<ConexoesView />)
    expect(screen.getByTestId('garmin-card')).toBeInTheDocument()
  })
})
```

Criar `web/components/__tests__/Sidebar.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { NAV_ITEMS } from '@/components/Sidebar'

describe('Sidebar NAV_ITEMS', () => {
  it('inclui o item Conexões apontando para /conexoes', () => {
    const item = NAV_ITEMS.find((i) => i.href === '/conexoes')
    expect(item).toBeDefined()
    expect(item?.label).toBe('Conexões')
  })

  it('Conexões vem logo após Importar', () => {
    const importar = NAV_ITEMS.findIndex((i) => i.href === '/importar')
    const conexoes = NAV_ITEMS.findIndex((i) => i.href === '/conexoes')
    expect(conexoes).toBe(importar + 1)
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/conexoes components/__tests__/Sidebar.test.tsx`
Expected: FAIL — `ConexoesView` inexistente e o item de nav ausente

- [ ] **Step 3: Implementar**

Criar `web/components/conexoes/ConexoesView.tsx`:

```tsx
"use client";
import { GarminCard } from '@/components/importar/GarminCard'

export function ConexoesView() {
  return (
    <div className="animate-fade-in space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100 sm:text-2xl">Conexões</h1>
        <p className="text-sm text-slate-500">
          Conecte seus dispositivos para importar treinos e recuperação automaticamente.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <GarminCard />
      </div>
    </div>
  )
}
```

Criar `web/app/(app)/conexoes/page.tsx`:

```tsx
import { ConexoesView } from "@/components/conexoes/ConexoesView";

export default function ConexoesPage() {
  return <ConexoesView />;
}
```

Em `web/components/Sidebar.tsx`: adicionar `Plug` à lista de imports do lucide-react (junto de `Upload` etc.):

```tsx
  Upload,
  Plug,
```

e o item em `NAV_ITEMS`, logo após a linha de "Importar":

```tsx
  { label: "Importar", href: "/importar", icon: Upload },
  { label: "Conexões", href: "/conexoes", icon: Plug },
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run components/conexoes components/__tests__/Sidebar.test.tsx`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add web/components/conexoes web/app/\(app\)/conexoes web/components/Sidebar.tsx web/components/__tests__/Sidebar.test.tsx
git commit -m "feat(web): página Conexões dedicada + item no menu

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Importar sem o card + link para Conexões

**Files:**
- Modify: `web/components/importar/ImportarView.tsx` (remove `GarminCard`, adiciona link)
- Modify: `web/components/importar/__tests__/ImportarView.test.tsx` (ausência do card + presença do link)

**Interfaces:**
- Consumes: nada novo. Depende de que a rota `/conexoes` exista (Task 1).
- Produces: `ImportarView` não renderiza mais `GarminCard`; contém um `<Link href="/conexoes">`.

- [ ] **Step 1: Ajustar os testes (falham com o código atual)**

Substituir o conteúdo de `web/components/importar/__tests__/ImportarView.test.tsx` por:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ImportarView } from '@/components/importar/ImportarView'

describe('ImportarView', () => {
  it('renderiza o título e o botão Enviar desabilitado sem arquivos', () => {
    render(<ImportarView />)
    expect(screen.getByText('📥 Importar treinos')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Enviar/ })).toBeDisabled()
  })

  it('não renderiza mais o card do Garmin (mudou para Conexões)', () => {
    render(<ImportarView />)
    expect(screen.queryByTestId('garmin-card')).not.toBeInTheDocument()
  })

  it('tem um link para a página Conexões', () => {
    render(<ImportarView />)
    expect(screen.getByRole('link', { name: /Conexões/ })).toHaveAttribute('href', '/conexoes')
  })
})
```

(Removeu-se o `vi.mock` do GarminCard — não é mais renderizado aqui.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/importar/__tests__/ImportarView.test.tsx`
Expected: FAIL — o card ainda é renderizado e não há link

- [ ] **Step 3: Implementar**

Em `web/components/importar/ImportarView.tsx`:

1. Remover a linha de import do GarminCard:

```tsx
import { GarminCard } from '@/components/importar/GarminCard'
```

2. Adicionar `import Link from 'next/link'` no topo (junto dos outros imports).

3. Substituir a linha `<GarminCard />` (logo após o `<h1>📥 Importar treinos</h1>`) por:

```tsx
      <p className="text-sm text-slate-500">
        Conecte um dispositivo em{' '}
        <Link href="/conexoes" className="font-medium text-blue-600 underline">Conexões</Link>{' '}
        para importar treinos automaticamente.
      </p>
```

- [ ] **Step 4: Rodar e ver passar (suíte web completa + typecheck)**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: toda a suíte web verde; `tsc` sem erros

- [ ] **Step 5: Commit**

```bash
git add web/components/importar/ImportarView.tsx web/components/importar/__tests__/ImportarView.test.tsx
git commit -m "feat(web): Importar aponta para Conexões (card do Garmin saiu daqui)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
