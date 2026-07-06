# Garmin Connect UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Card "Garmin Connect" na página Importar do `web/` (Next.js) para o atleta conectar a conta, ver status, sincronizar sob demanda e desconectar — mais o ajuste 401→400 no backend para falha de credencial Garmin.

**Architecture:** Um único client component (`GarminCard`) com máquina de estados dirigida pelo `GET /garmin/status` via SWR. Mutations com `apiFetch` direto. Polling do sync reusa `pollDecision`. Backend: `POST /garmin/connect` e `/connect/mfa` passam a devolver 400 (não 401) para credencial/código Garmin inválido, porque o `apiFetch` desloga o usuário do app em qualquer 401.

**Tech Stack:** Next.js 15 App Router, React 19, SWR, Tailwind v4, vitest + @testing-library/react (web). FastAPI + pytest via Docker (backend).

**Spec:** `docs/superpowers/specs/2026-07-06-garmin-connect-ui-design.md`

## Global Constraints

- UI inteira em **pt-BR**.
- Reusar componentes existentes: `Card`/`Button`/`Input`/`Badge` de `web/components/ui/`; NÃO criar modal/drawer.
- Testes do backend rodam SÓ via Docker (não há Python no host):
  `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest <PATH> -q --no-header -p no:warnings"`
- Testes do web rodam no host: `cd web && npx vitest run <PATH>`.
- Branch de trabalho: `feat/garmin-connect-ui` (já existe, spec commitada).
- Commits terminam com `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Valores do enum de status (backend, verbatim): `AWAITING_MFA`, `CONNECTED`, `NEEDS_REAUTH`, `DISCONNECTED`.

---

### Task 1: Backend — 400 (não 401) para credencial Garmin inválida

**Files:**
- Modify: `backend/app/api/routes/garmin.py` (linhas ~57-58 e ~97-98)
- Modify: `backend/app/services/garmin/fake_client.py` (novos flags de erro)
- Test: `backend/app/tests/test_garmin/test_api.py`

**Interfaces:**
- Consumes: rotas e fakes existentes.
- Produces: `POST /garmin/connect` e `POST /garmin/connect/mfa` retornam **400** com `detail` string quando `GarminAuthError`. `FakeGarminClient` ganha kwargs `raise_auth_on_login: bool = False` e `raise_auth_on_mfa: bool = False`.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `backend/app/tests/test_garmin/test_api.py`:

```python
@pytest.mark.asyncio
async def test_connect_bad_credentials_returns_400(client_factory):
    """Credencial Garmin inválida é 400 — 401 é reservado à sessão do app
    (o apiFetch do frontend desloga o usuário em qualquer 401)."""
    fake = FakeGarminClient(raise_auth_on_login=True)
    async with client_factory(fake) as ac:
        r = await ac.post("/api/v1/garmin/connect",
                          json={"email": "e@x.com", "password": "bad"})
        assert r.status_code == 400
        assert r.json()["detail"]


@pytest.mark.asyncio
async def test_mfa_bad_code_returns_400(client_factory):
    fake = FakeGarminClient(needs_mfa=True, raise_auth_on_mfa=True)
    async with client_factory(fake) as ac:
        await ac.post("/api/v1/garmin/connect",
                      json={"email": "e@x.com", "password": "pw"})
        r = await ac.post("/api/v1/garmin/connect/mfa", json={"code": "000000"})
        assert r.status_code == 400
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_garmin/test_api.py -q --no-header -p no:warnings"`
Expected: FAIL — `TypeError: FakeGarminClient.__init__() got an unexpected keyword argument 'raise_auth_on_login'`

- [ ] **Step 3: Implementar**

Em `backend/app/services/garmin/fake_client.py`, no `__init__`, adicionar os kwargs (depois de `raise_auth_on_resume: bool = False,`):

```python
        raise_auth_on_login: bool = False,
        raise_auth_on_mfa: bool = False,
```

e as atribuições (junto das demais):

```python
        self._raise_auth_on_login = raise_auth_on_login
        self._raise_auth_on_mfa = raise_auth_on_mfa
```

No método `login`, primeira linha do corpo:

```python
        if self._raise_auth_on_login:
            raise GarminAuthError("bad garmin credentials")
```

No método `resume_mfa`, primeira linha do corpo:

```python
        if self._raise_auth_on_mfa:
            raise GarminAuthError("bad mfa code")
```

Em `backend/app/api/routes/garmin.py`, na rota `connect`, trocar:

```python
    except GarminAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
```

por:

```python
    except GarminAuthError as exc:
        # 400, não 401: 401 é reservado à sessão do app — o frontend desloga
        # o usuário em qualquer 401 (ver web/lib/api.ts).
        raise HTTPException(status_code=400, detail=str(exc))
```

Na rota `connect_mfa`, trocar o mesmo bloco `except GarminAuthError` de 401 para 400 (mesmo comentário não é necessário na segunda ocorrência):

```python
    except GarminAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

- [ ] **Step 4: Rodar e ver passar (suíte Garmin inteira + ruff)**

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests/test_garmin -q --no-header -p no:warnings; ruff check app/api/routes/garmin.py app/services/garmin/fake_client.py app/tests/test_garmin/test_api.py"`
Expected: todos os pontos verdes `[100%]` e `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/garmin.py backend/app/services/garmin/fake_client.py backend/app/tests/test_garmin/test_api.py
git commit -m "fix(garmin): 400 para credencial Garmin inválida (401 é da sessão do app)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Web — tipos, hook e GarminCard com estados de leitura

**Files:**
- Modify: `web/lib/types.ts` (adicionar ao final)
- Modify: `web/lib/hooks.ts` (adicionar ao final + import do tipo)
- Create: `web/components/importar/GarminCard.tsx`
- Test: `web/components/importar/__tests__/GarminCard.test.tsx`

**Interfaces:**
- Consumes: `jsonFetcher` de `@/lib/api`; `Card`/`Badge`/`Button` de `@/components/ui/*`.
- Produces:
  - `types.ts`: `GarminStatus = { status: 'AWAITING_MFA'|'CONNECTED'|'NEEDS_REAUTH'|'DISCONNECTED'; last_sync_at: string|null; needs_reauth: boolean; last_error: string|null }`, `GarminConnectResponse = { needs_mfa: boolean; status: string }`, `GarminSyncResponse = { task_id: string|null }`.
  - `hooks.ts`: `useGarminStatus(): SWRResponse<GarminStatus>`.
  - `GarminCard.tsx`: componente `GarminCard()` exportado nomeado. Nesta task ele renderiza: loading→skeleton, erro (503 ou qualquer)→`null`, `CONNECTED`→badge+última sincronização+botões (handlers chegam na Task 4), demais status→placeholder de form (substituído na Task 3 — o teste desta task NÃO cobre esses status).

- [ ] **Step 1: Escrever os testes que falham**

Criar `web/components/importar/__tests__/GarminCard.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { GarminCard } from '@/components/importar/GarminCard'
import { useGarminStatus } from '@/lib/hooks'
import type { GarminStatus } from '@/lib/types'

vi.mock('@/lib/hooks', () => ({ useGarminStatus: vi.fn() }))
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))

const statusOf = (over: Partial<GarminStatus>): GarminStatus => ({
  status: 'DISCONNECTED', last_sync_at: null, needs_reauth: false, last_error: null, ...over,
})

function mockHook(v: { data?: GarminStatus; error?: unknown; isLoading?: boolean }) {
  ;(useGarminStatus as Mock).mockReturnValue({
    data: v.data, error: v.error, isLoading: v.isLoading ?? false, mutate: vi.fn(),
  })
}

beforeEach(() => vi.clearAllMocks())

describe('GarminCard — estados de leitura', () => {
  it('não renderiza nada quando a feature está desligada (503)', () => {
    mockHook({ error: { status: 503 } })
    const { container } = render(<GarminCard />)
    expect(container).toBeEmptyDOMElement()
  })

  it('não renderiza nada em erro desconhecido de status', () => {
    mockHook({ error: new Error('boom') })
    const { container } = render(<GarminCard />)
    expect(container).toBeEmptyDOMElement()
  })

  it('mostra skeleton enquanto carrega', () => {
    mockHook({ isLoading: true })
    render(<GarminCard />)
    expect(screen.getByTestId('garmin-skeleton')).toBeInTheDocument()
  })

  it('CONNECTED sem sync mostra "nunca"', () => {
    mockHook({ data: statusOf({ status: 'CONNECTED' }) })
    render(<GarminCard />)
    expect(screen.getByText('Conectado')).toBeInTheDocument()
    expect(screen.getByText(/nunca/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Sincronizar agora/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Desconectar/ })).toBeInTheDocument()
  })

  it('CONNECTED com sync recente mostra tempo relativo', () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 3600_000).toISOString()
    mockHook({ data: statusOf({ status: 'CONNECTED', last_sync_at: twoHoursAgo }) })
    render(<GarminCard />)
    expect(screen.getByText(/há 2 h/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/importar/__tests__/GarminCard.test.tsx`
Expected: FAIL — `Cannot find module '@/components/importar/GarminCard'` (ou equivalente de resolução)

- [ ] **Step 3: Implementar tipos, hook e componente**

Em `web/lib/types.ts`, adicionar ao final:

```ts
// --- Garmin Connect ---
export type GarminStatus = {
  status: 'AWAITING_MFA' | 'CONNECTED' | 'NEEDS_REAUTH' | 'DISCONNECTED'
  last_sync_at: string | null
  needs_reauth: boolean
  last_error: string | null
}
export type GarminConnectResponse = { needs_mfa: boolean; status: string }
export type GarminSyncResponse = { task_id: string | null }
```

Em `web/lib/hooks.ts`: adicionar `GarminStatus` ao import de tipos existente e, ao final do arquivo:

```ts
export function useGarminStatus() {
  // 503 = feature desligada — não adianta re-tentar.
  return useSWR<GarminStatus>('garmin/status', jsonFetcher as (p: string) => Promise<GarminStatus>, {
    shouldRetryOnError: false,
  })
}
```

Criar `web/components/importar/GarminCard.tsx`:

```tsx
"use client";
import { useEffect, useRef, useState } from 'react'
import { Watch } from 'lucide-react'
import { useGarminStatus } from '@/lib/hooks'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

/** "há 5 min" / "há 2 h" / data curta / "nunca" — para last_sync_at. */
export function fmtLastSync(iso: string | null): string {
  if (!iso) return 'nunca'
  const min = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
  if (min < 1) return 'agora mesmo'
  if (min < 60) return `há ${min} min`
  const h = Math.floor(min / 60)
  if (h < 48) return `há ${h} h`
  return new Date(iso).toLocaleDateString('pt-BR')
}

const TITLE = (
  <span className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100">
    <Watch className="h-4 w-4" /> Garmin Connect
  </span>
)

export function GarminCard() {
  const { data, error, isLoading, mutate } = useGarminStatus()
  const cancelled = useRef(false)
  useEffect(() => () => { cancelled.current = true }, [])
  // `mutate` e `cancelled` são usados pelos fluxos de conexão/sync (Tasks 3-4).
  void mutate

  if (error) return null // 503 (feature desligada) ou status indisponível — sem card
  if (isLoading || !data) {
    return (
      <Card title={TITLE}>
        <div data-testid="garmin-skeleton" className="h-10 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
      </Card>
    )
  }

  if (data.status === 'CONNECTED') {
    return (
      <Card title={TITLE} action={<Badge variant="success">Conectado</Badge>}>
        <div className="space-y-3">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Última sincronização: {fmtLastSync(data.last_sync_at)}. A sincronização
            automática roda diariamente.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button type="button">Sincronizar agora</Button>
            <Button type="button" variant="secondary">Desconectar</Button>
          </div>
        </div>
      </Card>
    )
  }

  // DISCONNECTED / AWAITING_MFA / NEEDS_REAUTH — implementados na Task 3.
  return (
    <Card title={TITLE}>
      <p className="text-sm text-slate-500">Conexão Garmin indisponível.</p>
    </Card>
  )
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run components/importar/__tests__/GarminCard.test.tsx`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add web/lib/types.ts web/lib/hooks.ts web/components/importar/GarminCard.tsx web/components/importar/__tests__/GarminCard.test.tsx
git commit -m "feat(web): GarminCard — status da conexão Garmin na página Importar

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Web — fluxo conectar (credenciais + consentimento) e MFA

**Files:**
- Modify: `web/components/importar/GarminCard.tsx`
- Test: `web/components/importar/__tests__/GarminCard.test.tsx` (novo `describe`)

**Interfaces:**
- Consumes: `apiFetch` de `@/lib/api`; `GarminConnectResponse` de `@/lib/types`; `Input` de `@/components/ui/Input`; `mutate` do SWR (Task 2).
- Produces: estados DISCONNECTED (form email/senha + checkbox de consentimento), AWAITING_MFA (código + "Recomeçar") e NEEDS_REAUTH (form sem checkbox, badge âmbar + `last_error`) funcionais.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao `GarminCard.test.tsx` (junto aos imports existentes, acrescentar `fireEvent`, `waitFor` de `@testing-library/react` e `apiFetch` de `@/lib/api`):

```tsx
const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

describe('GarminCard — conectar e MFA', () => {
  it('DISCONNECTED: botão Conectar só habilita com consentimento e campos', () => {
    mockHook({ data: statusOf({ status: 'DISCONNECTED' }) })
    render(<GarminCard />)
    const btn = screen.getByRole('button', { name: /Conectar/ })
    expect(btn).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Email da conta Garmin'), { target: { value: 'a@b.c' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'pw' } })
    expect(btn).toBeDisabled() // ainda falta o consentimento
    fireEvent.click(screen.getByRole('checkbox'))
    expect(btn).toBeEnabled()
  })

  it('connect com 400 mostra erro inline e não navega', async () => {
    mockHook({ data: statusOf({ status: 'DISCONNECTED' }) })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ detail: 'bad' }, 400))
    render(<GarminCard />)
    fireEvent.change(screen.getByLabelText('Email da conta Garmin'), { target: { value: 'a@b.c' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /Conectar/ }))
    expect(await screen.findByText('Email ou senha da Garmin inválidos.')).toBeInTheDocument()
  })

  it('connect ok revalida o status', async () => {
    const mutate = vi.fn()
    ;(useGarminStatus as Mock).mockReturnValue({
      data: statusOf({ status: 'DISCONNECTED' }), error: undefined, isLoading: false, mutate,
    })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ needs_mfa: false, status: 'CONNECTED' }))
    render(<GarminCard />)
    fireEvent.change(screen.getByLabelText('Email da conta Garmin'), { target: { value: 'a@b.c' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /Conectar/ }))
    await waitFor(() => expect(mutate).toHaveBeenCalled())
    expect(apiFetch).toHaveBeenCalledWith('garmin/connect', expect.objectContaining({ method: 'POST' }))
  })

  it('AWAITING_MFA mostra campo de código e envia para connect/mfa', async () => {
    const mutate = vi.fn()
    ;(useGarminStatus as Mock).mockReturnValue({
      data: statusOf({ status: 'AWAITING_MFA' }), error: undefined, isLoading: false, mutate,
    })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ needs_mfa: false, status: 'CONNECTED' }))
    render(<GarminCard />)
    fireEvent.change(screen.getByLabelText('Código de verificação (MFA)'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirmar código/ }))
    await waitFor(() => expect(mutate).toHaveBeenCalled())
    expect(apiFetch).toHaveBeenCalledWith('garmin/connect/mfa', expect.objectContaining({ method: 'POST' }))
  })

  it('MFA expirado (409) volta ao form de credenciais com aviso', async () => {
    mockHook({ data: statusOf({ status: 'AWAITING_MFA' }) })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ detail: 'MFA expired' }, 409))
    render(<GarminCard />)
    fireEvent.change(screen.getByLabelText('Código de verificação (MFA)'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirmar código/ }))
    expect(await screen.findByText('Tempo esgotado — conecte de novo.')).toBeInTheDocument()
    expect(screen.getByLabelText('Email da conta Garmin')).toBeInTheDocument()
  })

  it('NEEDS_REAUTH mostra badge âmbar, last_error e form sem checkbox', () => {
    mockHook({ data: statusOf({ status: 'NEEDS_REAUTH', needs_reauth: true, last_error: 'token expirou' }) })
    render(<GarminCard />)
    expect(screen.getByText('Reconexão necessária')).toBeInTheDocument()
    expect(screen.getByText(/token expirou/)).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Email da conta Garmin')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/importar/__tests__/GarminCard.test.tsx`
Expected: FAIL nos novos testes (`Unable to find a label with the text of: Email da conta Garmin`); os 5 da Task 2 seguem passando

- [ ] **Step 3: Implementar os fluxos**

Em `GarminCard.tsx`: acrescentar aos imports `type FormEvent` (react), `apiFetch` (`@/lib/api`) e `Input` (`@/components/ui/Input`). Dentro de `GarminCard()`, substituir a linha `void mutate` pelo estado e handlers:

```tsx
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [consent, setConsent] = useState(false)
  const [code, setCode] = useState('')
  const [restart, setRestart] = useState(false) // "Recomeçar"/409: força o form de credenciais
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  function failMessage(status: number, ctx: 'connect' | 'mfa'): string {
    if (status === 400) {
      return ctx === 'connect' ? 'Email ou senha da Garmin inválidos.' : 'Código incorreto ou expirado.'
    }
    if (status === 429) return 'Muitas tentativas — aguarde alguns minutos.'
    return 'Erro ao conectar. Tente novamente.'
  }

  async function connect(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setFormError(null)
    try {
      const res = await apiFetch('garmin/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (!res.ok) { setFormError(failMessage(res.status, 'connect')); return }
      setPassword(''); setRestart(false)
      await mutate()
    } catch {
      setFormError('Erro ao conectar. Tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  async function submitMfa(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setFormError(null)
    try {
      const res = await apiFetch('garmin/connect/mfa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
      if (res.status === 409) { setFormError('Tempo esgotado — conecte de novo.'); setRestart(true); return }
      if (!res.ok) { setFormError(failMessage(res.status, 'mfa')); return }
      setCode('')
      await mutate()
    } catch {
      setFormError('Erro ao conectar. Tente novamente.')
    } finally {
      setBusy(false)
    }
  }
```

Depois do bloco `if (data.status === 'CONNECTED') {...}`, substituir o `return` placeholder da Task 2 por:

```tsx
  const reauth = data.status === 'NEEDS_REAUTH'

  if (data.status === 'AWAITING_MFA' && !restart) {
    return (
      <Card title={TITLE} action={<Badge variant="info">Aguardando código</Badge>}>
        <form onSubmit={submitMfa} className="space-y-3">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Digite o código enviado pela Garmin (vale ~5 minutos).
          </p>
          <div className="max-w-xs">
            <Input
              label="Código de verificação (MFA)"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputMode="numeric"
              maxLength={6}
              autoFocus
            />
          </div>
          {formError && <p className="text-sm text-red-600">{formError}</p>}
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={busy || code.length < 6}>
              {busy ? 'Confirmando…' : 'Confirmar código'}
            </Button>
            <button
              type="button"
              onClick={() => { setRestart(true); setFormError(null) }}
              className="text-sm text-slate-500 underline hover:text-slate-700 dark:hover:text-slate-300"
            >
              Recomeçar
            </button>
          </div>
        </form>
      </Card>
    )
  }

  // DISCONNECTED, NEEDS_REAUTH, ou "Recomeçar" do MFA — form de credenciais
  const canSubmit = email.trim() !== '' && password !== '' && (consent || reauth) && !busy
  return (
    <Card
      title={TITLE}
      action={reauth ? <Badge variant="warning">Reconexão necessária</Badge> : undefined}
    >
      <form onSubmit={connect} className="space-y-3">
        {reauth ? (
          <p className="text-sm text-amber-600 dark:text-amber-400">
            A conexão com a Garmin expirou{data.last_error ? ` (${data.last_error})` : ''}.
            Entre de novo para reativar a sincronização.
          </p>
        ) : (
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Conecte sua conta para importar atividades e recuperação diariamente e
            enviar treinos aceitos direto ao calendário do seu Garmin.
          </p>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Input
            label="Email da conta Garmin"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="off"
          />
          <Input
            label="Senha"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="off"
          />
        </div>
        {!reauth && (
          <label className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-300">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              Autorizo o uso das minhas credenciais para sincronizar com o Garmin
              Connect (integração não-oficial). A senha não fica armazenada.
            </span>
          </label>
        )}
        {formError && <p className="text-sm text-red-600">{formError}</p>}
        <Button type="submit" disabled={!canSubmit}>
          {busy ? 'Conectando…' : reauth ? 'Reconectar' : 'Conectar'}
        </Button>
      </form>
    </Card>
  )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run components/importar/__tests__/GarminCard.test.tsx`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add web/components/importar/GarminCard.tsx web/components/importar/__tests__/GarminCard.test.tsx
git commit -m "feat(web): GarminCard — fluxo conectar com consentimento e MFA

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Web — Sincronizar agora (polling) e Desconectar (confirmação)

**Files:**
- Modify: `web/components/importar/GarminCard.tsx` (estado CONNECTED)
- Test: `web/components/importar/__tests__/GarminCard.test.tsx` (novo `describe`)

**Interfaces:**
- Consumes: `pollDecision` de `@/lib/jobPoll`; `GarminSyncResponse`, `JobStatus` de `@/lib/types`; `sleep` e `cancelled` (Task 2).
- Produces: `Sincronizar agora` → `POST garmin/sync` + polling `GET jobs/{task_id}` (2 s, máx. 120 ≈ 4 min) + revalidação; `Desconectar` → confirmação inline → `DELETE garmin/disconnect` + revalidação.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao `GarminCard.test.tsx`:

```tsx
describe('GarminCard — sincronizar e desconectar', () => {
  it('sincronizar agora: SUCCESS revalida e mostra confirmação', async () => {
    const mutate = vi.fn()
    ;(useGarminStatus as Mock).mockReturnValue({
      data: statusOf({ status: 'CONNECTED' }), error: undefined, isLoading: false, mutate,
    })
    ;(apiFetch as Mock).mockImplementation(async (path: string) => {
      if (path === 'garmin/sync') return jsonRes({ task_id: 't1' })
      if (path === 'jobs/t1') return jsonRes({ task_id: 't1', state: 'SUCCESS' })
      throw new Error(`unexpected ${path}`)
    })
    render(<GarminCard />)
    fireEvent.click(screen.getByRole('button', { name: /Sincronizar agora/ }))
    expect(await screen.findByText('Sincronizado ✓')).toBeInTheDocument()
    expect(mutate).toHaveBeenCalled()
  })

  it('sincronizar agora: FAILURE mostra mensagem de falha', async () => {
    mockHook({ data: statusOf({ status: 'CONNECTED' }) })
    ;(apiFetch as Mock).mockImplementation(async (path: string) => {
      if (path === 'garmin/sync') return jsonRes({ task_id: 't1' })
      return jsonRes({ task_id: 't1', state: 'FAILURE' })
    })
    render(<GarminCard />)
    fireEvent.click(screen.getByRole('button', { name: /Sincronizar agora/ }))
    expect(await screen.findByText(/sincronização falhou/)).toBeInTheDocument()
  })

  it('sincronizar agora: task_id null (broker fora) mostra falha', async () => {
    mockHook({ data: statusOf({ status: 'CONNECTED' }) })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ task_id: null }))
    render(<GarminCard />)
    fireEvent.click(screen.getByRole('button', { name: /Sincronizar agora/ }))
    expect(await screen.findByText(/sincronização falhou/)).toBeInTheDocument()
  })

  it('desconectar exige confirmação inline antes do DELETE', async () => {
    const mutate = vi.fn()
    ;(useGarminStatus as Mock).mockReturnValue({
      data: statusOf({ status: 'CONNECTED' }), error: undefined, isLoading: false, mutate,
    })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes(null, 204))
    render(<GarminCard />)
    fireEvent.click(screen.getByRole('button', { name: /Desconectar/ }))
    expect(apiFetch).not.toHaveBeenCalled()
    expect(screen.getByText(/Confirmar desconexão\?/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^Sim$/ }))
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('garmin/disconnect', expect.objectContaining({ method: 'DELETE' })))
    expect(mutate).toHaveBeenCalled()
  })

  it('cancelar desconexão volta aos botões normais sem DELETE', () => {
    mockHook({ data: statusOf({ status: 'CONNECTED' }) })
    render(<GarminCard />)
    fireEvent.click(screen.getByRole('button', { name: /Desconectar/ }))
    fireEvent.click(screen.getByRole('button', { name: /Cancelar/ }))
    expect(apiFetch).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /Sincronizar agora/ })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/importar/__tests__/GarminCard.test.tsx`
Expected: FAIL nos 5 novos (botões ainda sem handler); os 11 anteriores passam

- [ ] **Step 3: Implementar**

Em `GarminCard.tsx`: acrescentar aos imports `pollDecision` (`@/lib/jobPoll`) e os tipos `GarminSyncResponse`, `JobStatus` (`@/lib/types`). Junto aos estados existentes:

```tsx
  type SyncState = 'idle' | 'running' | 'done' | 'failed'
  const [syncState, setSyncState] = useState<SyncState>('idle')
  const [confirmingDisconnect, setConfirmingDisconnect] = useState(false)

  async function syncNow() {
    setSyncState('running')
    try {
      const res = await apiFetch('garmin/sync', { method: 'POST' })
      const body = (await res.json()) as GarminSyncResponse
      if (!res.ok || !body.task_id) { setSyncState('failed'); return }
      const max = 120 // ~4 min a cada 2 s — o 1º sync do piloto levou 3min18s
      for (let attempt = 1; attempt <= max; attempt++) {
        if (cancelled.current) return
        let state = 'PENDING'
        try {
          const r = await apiFetch(`jobs/${body.task_id}`)
          if (r.ok) state = ((await r.json()) as JobStatus).state
        } catch { /* trata como PENDING e segue */ }
        const d = pollDecision(state, attempt, max)
        if (d === 'done') { setSyncState('done'); await mutate(); return }
        if (d !== 'continue') { setSyncState('failed'); return }
        await sleep(2000)
      }
    } catch {
      setSyncState('failed')
    }
  }

  async function disconnect() {
    try {
      await apiFetch('garmin/disconnect', { method: 'DELETE' })
      setConfirmingDisconnect(false)
      await mutate()
    } catch { /* status revalida no próximo foco */ }
  }
```

No bloco `if (data.status === 'CONNECTED')`, substituir a `div` dos botões por:

```tsx
          {confirmingDisconnect ? (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-slate-600 dark:text-slate-300">Confirmar desconexão?</span>
              <Button type="button" variant="secondary" onClick={disconnect}>Sim</Button>
              <Button type="button" variant="ghost" onClick={() => setConfirmingDisconnect(false)}>Cancelar</Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" onClick={syncNow} disabled={syncState === 'running'}>
                {syncState === 'running' ? 'Sincronizando…' : 'Sincronizar agora'}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setConfirmingDisconnect(true)}>
                Desconectar
              </Button>
              {syncState === 'done' && <span className="text-sm text-emerald-600">Sincronizado ✓</span>}
              {syncState === 'failed' && (
                <span className="text-sm text-red-600">
                  A sincronização falhou ou está demorando — os dados chegam no sync diário automático.
                </span>
              )}
            </div>
          )}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run components/importar/__tests__/GarminCard.test.tsx`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add web/components/importar/GarminCard.tsx web/components/importar/__tests__/GarminCard.test.tsx
git commit -m "feat(web): GarminCard — sincronizar agora com polling e desconectar

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Integração na página Importar + suítes completas

**Files:**
- Modify: `web/components/importar/ImportarView.tsx` (render do card)
- Modify: `web/components/importar/__tests__/ImportarView.test.tsx`

**Interfaces:**
- Consumes: `GarminCard` (Task 2-4).
- Produces: página Importar renderiza `<GarminCard />` entre o título e o card de upload.

- [ ] **Step 1: Escrever o teste que falha**

Em `ImportarView.test.tsx`, mockar o GarminCard (evita SWR real no teste) e assertar a presença. Arquivo completo após a mudança:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ImportarView } from '@/components/importar/ImportarView'

vi.mock('@/components/importar/GarminCard', () => ({
  GarminCard: () => <div data-testid="garmin-card" />,
}))

describe('ImportarView', () => {
  it('renderiza o título e o botão Enviar desabilitado sem arquivos', () => {
    render(<ImportarView />)
    expect(screen.getByText('📥 Importar treinos')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Enviar/ })).toBeDisabled()
  })

  it('renderiza o card de conexão Garmin', () => {
    render(<ImportarView />)
    expect(screen.getByTestId('garmin-card')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run components/importar/__tests__/ImportarView.test.tsx`
Expected: FAIL — `Unable to find an element by: [data-testid="garmin-card"]`

- [ ] **Step 3: Implementar**

Em `ImportarView.tsx`, adicionar o import:

```tsx
import { GarminCard } from '@/components/importar/GarminCard'
```

e no JSX, logo após o `<h1 …>📥 Importar treinos</h1>`:

```tsx
      <GarminCard />
```

- [ ] **Step 4: Rodar as suítes completas (web + backend) e o lint**

Run: `cd web && npx vitest run && npm run lint --if-present`
Expected: todos os testes web passam; lint sem erros

Run: `docker run --rm -v "$(pwd -W)/backend":/app aath-backend:latest sh -c "pip install -q -e '.[dev]' 2>/dev/null; python -m pytest app/tests -q --no-header -p no:warnings 2>&1 | tail -2"`
Expected: suíte backend inteira verde

- [ ] **Step 5: Commit**

```bash
git add web/components/importar/ImportarView.tsx web/components/importar/__tests__/ImportarView.test.tsx
git commit -m "feat(web): card Garmin Connect integrado à página Importar

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
