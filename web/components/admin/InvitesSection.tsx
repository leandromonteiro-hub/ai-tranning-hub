"use client";
import { useState } from 'react'
import { Ticket } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { useInvites } from '@/lib/hooks'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

export function InvitesSection() {
  const { data, isLoading, mutate } = useInvites()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState<string | null>(null)

  async function generate() {
    setBusy(true); setError('')
    try {
      const res = await apiFetch('admin/invites', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: 5 }),
      })
      if (!res.ok) { setError('Falha ao gerar convites.'); return }
      await mutate()
    } catch {
      setError('Falha ao gerar convites.')
    } finally {
      setBusy(false)
    }
  }

  async function copy(code: string) {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(code)
      setTimeout(() => setCopied(null), 1500)
    } catch { /* clipboard indisponível — sem feedback */ }
  }

  return (
    <Card
      title={
        <span className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100">
          <Ticket className="h-4 w-4" /> Convites do piloto
        </span>
      }
      action={
        <Button type="button" onClick={generate} disabled={busy}>
          {busy ? 'Gerando…' : 'Gerar 5 convites'}
        </Button>
      }
    >
      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
      {isLoading ? (
        <p className="text-sm text-slate-500">Carregando…</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-400">
                <th className="font-normal">Código</th>
                <th className="font-normal">Status</th>
                <th className="font-normal">Usado por</th>
                <th className="font-normal" />
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((i) => (
                <tr key={i.code} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1.5 font-mono text-slate-700 dark:text-slate-200">{i.code}</td>
                  <td className="py-1.5">
                    {i.used_at ? <Badge variant="info">Usado</Badge> : <Badge variant="success">Livre</Badge>}
                  </td>
                  <td className="py-1.5 text-slate-500">{i.used_by_email ?? '—'}</td>
                  <td className="py-1.5 text-right">
                    {!i.used_at && (
                      <button
                        type="button"
                        onClick={() => copy(i.code)}
                        className="text-xs text-slate-500 underline hover:text-slate-700 dark:hover:text-slate-300"
                      >
                        {copied === i.code ? 'Copiado ✓' : 'Copiar'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(data ?? []).length === 0 && (
            <p className="py-2 text-sm text-slate-500">Nenhum convite ainda — gere os primeiros.</p>
          )}
        </div>
      )}
    </Card>
  )
}
