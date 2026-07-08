# Prontidão do onboarding para o piloto Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar dois furos do onboarding antes do piloto: (A) o wizard exige os 9 campos obrigatórios da anamnese; (B) o wizard ganha um passo guiado de importar histórico (que constrói o twin).

**Architecture:** Tudo em `web/`, zero backend. Um helper de completude da anamnese trava o passo 1 do wizard. O upload de arquivos (hoje dentro do `ImportarView`) é extraído para um `FileUploader` reutilizável, usado tanto na página Importar quanto num novo passo do wizard.

**Tech Stack:** Next.js 15 + React 19 + Tailwind; vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-07-08-onboarding-prontidao-piloto-design.md`

## Global Constraints

- pt-BR; zero backend novo; reusar componentes existentes.
- Testes web no host: `cd web && npx vitest run <PATH>`.
- Branch: `feat/onboarding-prontidao` (já existe, spec commitada).
- Commits terminam com `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- 9 campos obrigatórios (verbatim, espelham backend `REQUIRED_FIELDS`): `birth_date, sex, weight_kg, height_cm, max_hr, primary_discipline, years_training, goals, weekly_hours`.
- Ordem final dos passos do wizard (verbatim): `['Anamnese', 'Importar histórico', 'Garmin', 'Concluir']`.

---

### Task 1: Validar a anamnese no wizard (Furo A)

**Files:**
- Modify: `web/lib/anamnese.ts` (add `isAnamneseComplete` + `missingRequiredFields`)
- Modify: `web/components/onboarding/OnboardingWizard.tsx` (`advanceFromAnamnese`)
- Test: `web/lib/__tests__/anamnese.test.ts`

**Interfaces:**
- Consumes: `AthleteProfile` de `@/lib/types`.
- Produces:
  - `isAnamneseComplete(profile: AthleteProfile | null | undefined): boolean`
  - `missingRequiredFields(profile: AthleteProfile | null | undefined): string[]` (rótulos pt-BR dos que faltam).

- [ ] **Step 1: Escrever os testes que falham**

Criar `web/lib/__tests__/anamnese.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { isAnamneseComplete, missingRequiredFields } from '@/lib/anamnese'
import type { AthleteProfile } from '@/lib/types'

const full: AthleteProfile = {
  id: 'p', athlete_id: 'a',
  birth_date: '1990-01-01', sex: 'M', weight_kg: 70, height_cm: 175,
  max_hr: 185, resting_hr: 50, primary_discipline: 'XCM', years_training: 5,
  notes: null, goals: 'ultra', weekly_hours: 10, weekly_days: 5,
  injury_history: null, medical_conditions: null,
  has_power_meter: true, has_hr_monitor: true,
}

describe('isAnamneseComplete', () => {
  it('true quando os 9 obrigatórios estão preenchidos', () => {
    expect(isAnamneseComplete(full)).toBe(true)
  })
  it('false faltando qualquer obrigatório', () => {
    expect(isAnamneseComplete({ ...full, weekly_hours: null })).toBe(false)
    expect(isAnamneseComplete({ ...full, goals: '' as unknown as string })).toBe(false)
    expect(isAnamneseComplete(null)).toBe(false)
  })
  it('não exige os opcionais (resting_hr, weekly_days, lesões)', () => {
    expect(isAnamneseComplete({ ...full, resting_hr: null, weekly_days: null, injury_history: null })).toBe(true)
  })
})

describe('missingRequiredFields', () => {
  it('lista os rótulos dos que faltam', () => {
    const miss = missingRequiredFields({ ...full, weekly_hours: null, max_hr: null })
    expect(miss).toContain('Horas por semana')
    expect(miss).toContain('FC máxima')
    expect(miss).not.toContain('Peso')
  })
  it('null → todos os obrigatórios', () => {
    expect(missingRequiredFields(null)).toHaveLength(9)
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run lib/__tests__/anamnese.test.ts`
Expected: FAIL — `isAnamneseComplete`/`missingRequiredFields` inexistentes

- [ ] **Step 3: Implementar**

Em `web/lib/anamnese.ts`, adicionar ao final:

```ts
// Espelha backend REQUIRED_FIELDS (profile_context.py) — os 9 que travam a recomendação.
const REQUIRED: ReadonlyArray<[keyof AthleteProfile, string]> = [
  ['birth_date', 'Data de nascimento'],
  ['sex', 'Sexo'],
  ['weight_kg', 'Peso'],
  ['height_cm', 'Altura'],
  ['max_hr', 'FC máxima'],
  ['primary_discipline', 'Disciplina principal'],
  ['years_training', 'Anos de treino'],
  ['goals', 'Objetivos'],
  ['weekly_hours', 'Horas por semana'],
]

function _isFilled(v: unknown): boolean {
  return v !== null && v !== undefined && v !== ''
}

/** Rótulos pt-BR dos campos obrigatórios que ainda faltam. */
export function missingRequiredFields(profile: AthleteProfile | null | undefined): string[] {
  return REQUIRED.filter(([k]) => !_isFilled(profile?.[k])).map(([, label]) => label)
}

/** True quando os 9 campos obrigatórios da anamnese estão preenchidos. */
export function isAnamneseComplete(profile: AthleteProfile | null | undefined): boolean {
  return missingRequiredFields(profile).length === 0
}
```

Em `web/components/onboarding/OnboardingWizard.tsx`, no topo adicionar
`import { isAnamneseComplete, missingRequiredFields } from '@/lib/anamnese'` e
trocar o corpo de `advanceFromAnamnese`:

```tsx
  async function advanceFromAnamnese() {
    setBusy(true); setError('')
    try {
      const res = await apiFetch('athletes/me/profile')
      const profile = res.ok ? await res.json() : null
      if (!isAnamneseComplete(profile)) {
        const miss = missingRequiredFields(profile)
        setError(`Preencha os campos obrigatórios antes de continuar: ${miss.join(', ')}.`)
        return
      }
      setStep(1)
    } catch {
      setError('Não foi possível verificar seu perfil. Tente novamente.')
    } finally {
      setBusy(false)
    }
  }
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run lib/__tests__/anamnese.test.ts`
Expected: verde

- [ ] **Step 5: Commit**

```bash
git add web/lib/anamnese.ts web/lib/__tests__/anamnese.test.ts web/components/onboarding/OnboardingWizard.tsx
git commit -m "feat(onboarding): wizard exige a anamnese completa (9 campos) antes de avançar

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Extrair FileUploader do ImportarView

**Files:**
- Create: `web/components/importar/FileUploader.tsx`
- Modify: `web/components/importar/ImportarView.tsx` (usa o FileUploader)
- Test: `web/components/importar/__tests__/FileUploader.test.tsx`
- (o teste existente `ImportarView.test.tsx` deve continuar verde)

**Interfaces:**
- Consumes: `apiFetch`, `pollDecision`, tipos `JobStatus`/`UploadResponse`, `Card`.
- Produces: `FileUploader()` (named export) — o Card de envio + o Card de resultado + o polling da regeneração do perfil (lógica idêntica à que estava no ImportarView).

- [ ] **Step 1: Escrever o teste que falha**

Criar `web/components/importar/__tests__/FileUploader.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FileUploader } from '@/components/importar/FileUploader'

describe('FileUploader', () => {
  it('renderiza o input de arquivos e o botão Enviar desabilitado sem arquivos', () => {
    render(<FileUploader />)
    expect(screen.getByText(/Enviar arquivos/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Enviar/ })).toBeDisabled()
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/importar/__tests__/FileUploader.test.tsx`
Expected: FAIL — `FileUploader` inexistente

- [ ] **Step 3: Implementar**

Criar `web/components/importar/FileUploader.tsx` movendo a lógica de upload do
ImportarView (verbatim):

```tsx
"use client";
import { useEffect, useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { pollDecision } from '@/lib/jobPoll'
import type { JobStatus, UploadResponse } from '@/lib/types'
import { Card } from '@/components/ui/Card'

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))
type ProfileState = 'idle' | 'polling' | 'done' | 'failed' | 'giveup'

const PROFILE_MSG: Record<Exclude<ProfileState, 'idle'>, string> = {
  polling: '🔄 Atualizando seu perfil…',
  done: '✅ Perfil atualizado.',
  failed: 'O perfil será atualizado em instantes.',
  giveup: 'O perfil está sendo atualizado em segundo plano.',
}

export function FileUploader() {
  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<UploadResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [profile, setProfile] = useState<ProfileState>('idle')
  const cancelled = useRef(false)
  const pollGen = useRef(0)

  useEffect(() => () => { cancelled.current = true }, [])

  async function pollProfile(taskId: string) {
    const gen = ++pollGen.current
    const alive = () => !cancelled.current && pollGen.current === gen
    setProfile('polling')
    const max = 30
    for (let attempt = 1; attempt <= max; attempt++) {
      if (!alive()) return
      let state = 'PENDING'
      try {
        const r = await apiFetch(`jobs/${taskId}`)
        if (r.ok) state = ((await r.json()) as JobStatus).state
      } catch { /* trata como PENDING e segue */ }
      const d = pollDecision(state, attempt, max)
      if (d !== 'continue') { if (alive()) setProfile(d); return }
      await sleep(1500)
    }
  }

  async function upload() {
    if (files.length === 0) return
    setUploading(true); setError(null); setResult(null); setProfile('idle')
    try {
      const fd = new FormData()
      for (const f of files) fd.append('files', f)
      const res = await apiFetch('imports/upload', { method: 'POST', body: fd })
      if (!res.ok) { setError('Falha no upload. Verifique os arquivos e tente de novo.'); return }
      const body = (await res.json()) as UploadResponse
      setResult(body)
      if (body.profile_task_id) void pollProfile(body.profile_task_id)
    } catch {
      setError('Falha no upload. Tente de novo.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-5">
      <Card title="Enviar arquivos (CSV TrainingPeaks, FIT, TCX, GPX)">
        <div className="space-y-3">
          <input
            type="file"
            multiple
            accept=".csv,.fit,.tcx,.gpx"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-slate-800 dark:text-slate-300 dark:file:bg-slate-100 dark:file:text-slate-900"
          />
          {files.length > 0 && <p className="text-xs text-slate-500">{files.length} arquivo(s) selecionado(s)</p>}
          <button
            type="button"
            onClick={upload}
            disabled={uploading || files.length === 0}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Upload className="h-4 w-4" />
            {uploading ? 'Enviando…' : 'Enviar'}
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
      </Card>

      {result && (
        <Card title="Importação concluída">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-400">
                  <th className="font-normal">Arquivo</th><th className="font-normal">Formato</th>
                  <th className="font-normal">Status</th><th className="font-normal">Linhas</th>
                </tr>
              </thead>
              <tbody>
                {result.files.map((f) => (
                  <tr key={f.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1 text-slate-700 dark:text-slate-200">{f.filename}</td>
                    <td className="py-1 text-slate-500">{f.file_format}</td>
                    <td className="py-1 text-slate-500">{f.error_message ? `erro: ${f.error_message}` : f.status}</td>
                    <td className="py-1 text-slate-500">{f.rows_imported}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {profile !== 'idle' && (
            <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{PROFILE_MSG[profile]}</p>
          )}
        </Card>
      )}
    </div>
  )
}
```

Substituir `web/components/importar/ImportarView.tsx` por (fica só o cabeçalho + link + o FileUploader):

```tsx
"use client";
import Link from 'next/link'
import { FileUploader } from '@/components/importar/FileUploader'

export function ImportarView() {
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">📥 Importar treinos</h1>
      <p className="text-sm text-slate-500">
        Conecte um dispositivo em{' '}
        <Link href="/conexoes" className="font-medium text-blue-600 underline">Conexões</Link>{' '}
        para importar treinos automaticamente.
      </p>
      <FileUploader />
    </div>
  )
}
```

- [ ] **Step 4: Rodar e ver passar (FileUploader + ImportarView regressão)**

Run: `cd web && npx vitest run components/importar`
Expected: verde (o teste existente do ImportarView continua passando — o título e o botão Enviar seguem presentes via FileUploader)

- [ ] **Step 5: Commit**

```bash
git add web/components/importar/FileUploader.tsx web/components/importar/ImportarView.tsx web/components/importar/__tests__/FileUploader.test.tsx
git commit -m "refactor(web): extrai FileUploader do ImportarView (reuso no onboarding)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Passo "Importar histórico" no wizard (Furo B)

**Files:**
- Modify: `web/components/onboarding/OnboardingWizard.tsx`
- Test: `web/components/onboarding/__tests__/OnboardingWizard.test.tsx`

**Interfaces:**
- Consumes: `FileUploader` (Task 2); `isAnamneseComplete` (Task 1).
- Produces: wizard com 4 passos `['Anamnese', 'Importar histórico', 'Garmin', 'Concluir']`; o passo de histórico renderiza `<FileUploader />` e é pulável; Garmin agora é o passo 2, Concluir o passo 3.

- [ ] **Step 1: Ajustar os testes (falham com o fluxo atual de 3 passos)**

Atualizar `web/components/onboarding/__tests__/OnboardingWizard.test.tsx`. Além dos
mocks existentes de `AnamneseView`/`GarminCard`, mockar o FileUploader e cobrir o
novo fluxo. Conteúdo relevante (ajuste o arquivo para isto):

```tsx
vi.mock('@/components/importar/FileUploader', () => ({
  FileUploader: () => <div data-testid="file-uploader" />,
}))
```

Adicionar/ajustar testes:

```tsx
  it('passo 1 (anamnese) não avança com perfil incompleto', async () => {
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ birth_date: '1990-01-01' })) // faltam campos
    render(<OnboardingWizard />)
    fireEvent.click(screen.getByRole('button', { name: /Continuar/ }))
    expect(await screen.findByText(/Preencha os campos obrigatórios/)).toBeInTheDocument()
    expect(screen.queryByTestId('file-uploader')).not.toBeInTheDocument()
  })

  it('anamnese completa → passo Importar histórico (FileUploader), pulável → Garmin', async () => {
    const complete = {
      birth_date: '1990-01-01', sex: 'M', weight_kg: 70, height_cm: 175, max_hr: 185,
      primary_discipline: 'XCM', years_training: 5, goals: 'ultra', weekly_hours: 10,
    }
    ;(apiFetch as Mock).mockResolvedValue(jsonRes(complete))
    render(<OnboardingWizard />)
    fireEvent.click(screen.getByRole('button', { name: /Continuar/ }))
    expect(await screen.findByTestId('file-uploader')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Pular por enquanto/ }))
    expect(screen.getByTestId('garmin-card')).toBeInTheDocument()
  })
```

(Manter/adequar os testes já existentes que seguem o fluxo até Concluir: agora
há um passo a mais antes do Garmin — clicar "Pular"/"Continuar" no passo de
histórico entre a anamnese e o Garmin. Reusar o helper `jsonRes` e o mock de
`apiFetch` já presentes no arquivo.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/onboarding`
Expected: FAIL — não há passo de histórico / FileUploader

- [ ] **Step 3: Implementar**

Em `web/components/onboarding/OnboardingWizard.tsx`:

1. Import: `import { FileUploader } from '@/components/importar/FileUploader'`.

2. Trocar o array de passos:

```tsx
const STEPS = ['Anamnese', 'Importar histórico', 'Garmin', 'Concluir'] as const
```

3. Inserir o novo passo entre a anamnese (step 0) e o Garmin. O bloco do Garmin
passa a ser `step === 2` e o de Concluir `step === 3`. Substituir os blocos
`{step === 1 && ...}` (Garmin) e `{step === 2 && ...}` (Concluir) por:

```tsx
      {step === 1 && (
        <div className="space-y-4">
          <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">
            Importe seu histórico (opcional, recomendado)
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Quanto mais histórico você subir — export do TrainingPeaks/Strava ou
            arquivos FIT —, melhores e mais personalizadas ficam as recomendações.
            Dá para fazer depois na página Importar.
          </p>
          <FileUploader />
          <div className="flex gap-2">
            <Button type="button" onClick={() => setStep(2)}>Continuar</Button>
            <Button type="button" variant="secondary" onClick={() => setStep(2)}>
              Pular por enquanto
            </Button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">
            Conecte seu Garmin (opcional)
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Mantém seus treinos e recuperação atualizados automaticamente. Dá para fazer depois na página Conexões.
          </p>
          <GarminCard />
          <div className="flex gap-2">
            <Button type="button" onClick={() => setStep(3)}>Continuar</Button>
            <Button type="button" variant="secondary" onClick={() => setStep(3)}>
              Pular por enquanto
            </Button>
          </div>
        </div>
      )}

      {step === 3 && (
        <Card title="Tudo pronto 🎉">
          <div className="space-y-4">
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Seu perfil está criado. Se ainda não importou seu histórico, faça isso
              na página Importar para o treinador IA te conhecer mais rápido.
            </p>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button type="button" onClick={complete} disabled={busy}>
              {busy ? 'Concluindo…' : 'Começar a treinar'}
            </Button>
          </div>
        </Card>
      )}
```

- [ ] **Step 4: Rodar e ver passar (suíte web completa + tsc)**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: toda a suíte web verde; `tsc` limpo

- [ ] **Step 5: Commit**

```bash
git add web/components/onboarding/OnboardingWizard.tsx web/components/onboarding/__tests__/OnboardingWizard.test.tsx
git commit -m "feat(onboarding): passo de importar histórico no wizard (constrói o twin)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
