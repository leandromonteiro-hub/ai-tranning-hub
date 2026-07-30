"use client";
import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { apiFetch } from '@/lib/api'
import { useWhoopStatus } from '@/lib/hooks'
import type { WhoopAuthorizeResponse } from '@/lib/types'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

const TITLE = '⌚ Whoop'

/** Mensagens por motivo. A linha do limite de membros é o porquê deste mapa
 *  existir: um "falha ao conectar" genérico faria o operador depurar às cegas. */
const MOTIVO: Record<string, string> = {
  whoop_authorization_failed:
    'A Whoop recusou a autorização. Enquanto o app não for aprovado, a Whoop limita 10 atletas conectados — se esse limite foi atingido, é preciso desconectar alguém ou pedir aprovação.',
  whoop_unavailable: 'A Whoop não respondeu. Tente em alguns minutos.',
  whoop_token_key_missing: 'Integração incompleta no servidor (chave de criptografia ausente).',
  invalid_state: 'A autorização expirou. Clique em Conectar novamente.',
  not_connected: 'A conexão não está ativa.',
  sessao_expirada: 'Sua sessão expirou durante a autorização. Entre de novo e repita.',
  callback_incompleto: 'A Whoop não devolveu a autorização. Tente novamente.',
  access_denied: 'Você não autorizou o acesso na tela da Whoop.',
}

const GENERICO = 'Não foi possível concluir. Tente novamente.'

const fmtLastSync = (iso: string | null): string =>
  iso ? new Date(iso).toLocaleString('pt-BR') : 'nunca'

export function WhoopCard() {
  const { data, error, isLoading, mutate } = useWhoopStatus()
  const params = useSearchParams()
  const [busy, setBusy] = useState(false)
  const [motivo, setMotivo] = useState<string | null>(null)
  const [syncState, setSyncState] = useState<'idle' | 'sent' | 'failed'>('idle')

  // O erro da autorização acontece no callback (outra request, outro processo) e
  // volta na query string. Sem ler daqui, a mensagem do limite de 10 atletas —
  // o caso que o runbook promete explicar — nunca chegaria à tela.
  // params pode ser null fora de um contexto de router (renderização estática),
  // e um card de conexão não é motivo para derrubar a página inteira.
  const motivoDaUrl = params?.get('whoop') === 'erro' ? params.get('motivo') : null
  useEffect(() => {
    if (motivoDaUrl) setMotivo(MOTIVO[motivoDaUrl] ?? GENERICO)
  }, [motivoDaUrl])

  async function fail(res: Response) {
    const body = await res.json().catch(() => ({}))
    const detail = typeof body?.detail === 'string' ? body.detail : ''
    setMotivo(MOTIVO[detail] ?? GENERICO)
  }

  async function connect() {
    setBusy(true); setMotivo(null)
    try {
      const res = await apiFetch('whoop/authorize', { method: 'POST' })
      if (!res.ok) { await fail(res); return }
      const body = (await res.json()) as WhoopAuthorizeResponse
      // O navegador sai daqui para a Whoop; o retorno cai em /api/whoop/callback.
      window.location.href = body.authorize_url
    } catch {
      setMotivo('Erro ao conectar. Tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  async function syncNow() {
    setBusy(true); setMotivo(null); setSyncState('idle')
    try {
      const res = await apiFetch('whoop/sync', { method: 'POST' })
      if (!res.ok) { await fail(res); setSyncState('failed'); return }
      setSyncState('sent')
      await mutate()
    } catch {
      setSyncState('failed')
    } finally {
      setBusy(false)
    }
  }

  async function disconnect() {
    setBusy(true); setMotivo(null)
    try {
      const res = await apiFetch('whoop/connection', { method: 'DELETE' })
      if (!res.ok) { await fail(res); return }
      await mutate()
    } catch {
      setMotivo('Não foi possível desconectar. Tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  if (error) return null // 503 (feature desligada) ou status indisponível — sem card
  if (isLoading || !data) {
    return (
      <Card title={TITLE}>
        <div
          data-testid="whoop-skeleton"
          className="h-10 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800"
        />
      </Card>
    )
  }

  if (data.status === 'CONNECTED') {
    return (
      <Card title={TITLE} action={<Badge variant="success">Conectado</Badge>}>
        <div className="space-y-3">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            HRV, sono e recuperação. Última sincronização: {fmtLastSync(data.last_sync_at)}.
            A automática roda todo dia às 5h.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" onClick={syncNow} disabled={busy}>
              {busy ? 'Sincronizando…' : 'Sincronizar agora'}
            </Button>
            <Button type="button" variant="secondary" onClick={disconnect} disabled={busy}>
              Desconectar
            </Button>
            {syncState === 'sent' && (
              <span className="text-sm text-emerald-600">
                Sincronização enfileirada ✓
              </span>
            )}
          </div>
          {motivo && <p className="text-sm text-red-600">{motivo}</p>}
        </div>
      </Card>
    )
  }

  const reauth = data.status === 'NEEDS_REAUTH'
  return (
    <Card
      title={TITLE}
      action={reauth ? <Badge variant="warning">Reconexão necessária</Badge> : undefined}
    >
      <div className="space-y-3">
        {reauth ? (
          <p className="text-sm text-amber-600 dark:text-amber-400">
            A conexão com a Whoop caiu{data.last_error ? ` (${data.last_error})` : ''}.
            Autorize de novo para retomar a sincronização.
          </p>
        ) : (
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Conecte sua conta para importar HRV, sono e recuperação diariamente — o
            dado que o treinador IA usa para calibrar a carga. Você autoriza no site
            da Whoop; sua senha nunca passa por aqui.
          </p>
        )}
        <Button type="button" onClick={connect} disabled={busy}>
          {busy ? 'Abrindo…' : reauth ? 'Reconectar' : 'Conectar'}
        </Button>
        {motivo && <p className="text-sm text-red-600">{motivo}</p>}
      </div>
    </Card>
  )
}
