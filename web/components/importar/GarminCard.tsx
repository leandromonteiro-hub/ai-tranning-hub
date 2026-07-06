"use client";
import { FormEvent, useEffect, useRef, useState } from 'react'
import { Watch } from 'lucide-react'
import { useGarminStatus } from '@/lib/hooks'
import { apiFetch } from '@/lib/api'
import { pollDecision } from '@/lib/jobPoll'
import type { GarminSyncResponse, JobStatus } from '@/lib/types'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'

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

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [consent, setConsent] = useState(false)
  const [code, setCode] = useState('')
  const [restart, setRestart] = useState(false) // "Recomeçar"/409: força o form de credenciais
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  type SyncState = 'idle' | 'running' | 'done' | 'failed'
  const [syncState, setSyncState] = useState<SyncState>('idle')
  const [confirmingDisconnect, setConfirmingDisconnect] = useState(false)

  function failMessage(status: number, ctx: 'connect' | 'mfa'): string {
    if (status === 400) {
      return ctx === 'connect' ? 'Email ou senha da Garmin inválidos.' : 'Código incorreto ou expirado.'
    }
    if (status === 429) return 'Muitas tentativas — aguarde alguns minutos.'
    return 'Erro ao conectar. Tente novamente.'
  }

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
        </div>
      </Card>
    )
  }

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
}
