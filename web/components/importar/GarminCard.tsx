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
