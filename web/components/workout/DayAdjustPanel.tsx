"use client";
import { useState } from 'react'
import { RotateCcw, Sparkles } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { adjustPreview, adjustmentReason, canAdjust, type AdjustPreview } from '@/lib/dayAdjust'
import { formatDuration, formatTss } from '@/lib/format'
import { riskBadge } from '@/lib/recs'
import { todayIso } from '@/lib/dateUtils'
import type { PlannedWorkout, Recommendation } from '@/lib/types'
import { Badge } from '@/components/ui/Badge'

const btn =
  'rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50'

export function DayAdjustPanel({ planned, onChanged }: { planned: PlannedWorkout; onChanged: () => void }) {
  const [preview, setPreview] = useState<{ rec: Recommendation; p: AdjustPreview } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function requestAdjust() {
    setBusy(true); setError(null)
    try {
      const res = await apiFetch(`plans/workouts/${planned.id}/adjust`, { method: 'POST' })
      if (!res.ok) {
        setError(res.status === 409 ? 'Não é possível ajustar um dia passado.' : 'Não foi possível gerar o ajuste.')
        return
      }
      const rec = (await res.json()) as Recommendation
      setPreview({ rec, p: adjustPreview(rec) })
    } catch { setError('Não foi possível gerar o ajuste.') } finally { setBusy(false) }
  }

  async function accept() {
    if (!preview) return
    setBusy(true); setError(null)
    try {
      const res = await apiFetch(`plans/workouts/${planned.id}/apply-adjustment`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recommendation_id: preview.rec.id }),
      })
      if (!res.ok) { setError('Não foi possível aplicar o ajuste.'); return }
      // não zera o preview: deixa o planned.adjustment (que chega via onChanged)
      // dirigir a transição para o estado "ajustado" — evita flash do botão Ajustar.
      onChanged()
    } catch { setError('Não foi possível aplicar o ajuste.') } finally { setBusy(false) }
  }

  async function revert() {
    setBusy(true); setError(null)
    try {
      const res = await apiFetch(`plans/workouts/${planned.id}/adjustment`, { method: 'DELETE' })
      if (!res.ok) { setError('Não foi possível reverter.'); return }
      onChanged()
    } catch { setError('Não foi possível reverter.') } finally { setBusy(false) }
  }

  // 1) Já ajustado → motivo + reverter
  if (planned.adjustment) {
    return (
      <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm text-violet-800 dark:border-violet-500/40 dark:bg-violet-500/10 dark:text-violet-300">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>🤖 Treino ajustado pela IA. {adjustmentReason(planned.adjustment) ?? 'Valores efetivos refletem o ajuste do dia.'}</span>
          <button type="button" onClick={revert} disabled={busy} className={`${btn} border border-violet-300 text-violet-700 hover:bg-violet-100 dark:text-violet-200`}>
            <span className="flex items-center gap-1.5"><RotateCcw className="h-3.5 w-3.5" />Reverter ajuste</span>
          </button>
        </div>
        {error && <p className="mt-2 text-red-600">{error}</p>}
      </div>
    )
  }

  // 2) Preview gerado → aceitar / cancelar
  if (preview) {
    const badge = riskBadge(preview.p.riskLevel)
    return (
      <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm dark:border-violet-500/40 dark:bg-violet-500/10">
        <div className="mb-2 flex items-center gap-2">
          <Badge variant={badge.variant}>{badge.emoji} {badge.label}</Badge>
          <span className="font-semibold text-violet-800 dark:text-violet-200">Ajuste sugerido</span>
        </div>
        {preview.p.reason && <p className="mb-2 text-violet-800 dark:text-violet-200">{preview.p.reason}</p>}
        <div className="mb-3 grid grid-cols-2 gap-2 text-violet-900 dark:text-violet-100">
          <div><span className="text-violet-500">TSS:</span> {formatTss(planned.planned_tss)} → <strong>{formatTss(preview.p.adjustedTss)}</strong></div>
          <div><span className="text-violet-500">Duração:</span> {formatDuration(planned.planned_duration_s)} → <strong>{formatDuration(preview.p.adjustedDurationS)}</strong></div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={accept} disabled={busy} className={`${btn} bg-violet-600 text-white hover:bg-violet-700`}>Aceitar ajuste</button>
          <button type="button" onClick={() => setPreview(null)} disabled={busy} className={`${btn} border border-slate-300 text-slate-600 dark:border-slate-600 dark:text-slate-300`}>Cancelar</button>
        </div>
        {error && <p className="mt-2 text-red-600">{error}</p>}
      </div>
    )
  }

  // 3) Sem ajuste e é hoje/futuro → botão de gerar
  if (!canAdjust(planned, todayIso())) return null
  return (
    <div>
      <button type="button" onClick={requestAdjust} disabled={busy} className={`${btn} bg-violet-600 text-white hover:bg-violet-700`}>
        <span className="flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" />{busy ? 'Gerando ajuste…' : 'Ajustar com a IA'}</span>
      </button>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  )
}
