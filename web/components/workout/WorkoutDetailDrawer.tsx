"use client";
import { useEffect } from 'react'
import { X } from 'lucide-react'
import { useWorkoutStreams } from '@/lib/hooks'
import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'
import { structureToSegments, structureToSteps } from '@/lib/structure'
import { IntensityProfile } from '@/components/workout/IntensityProfile'
import { PlannedCompletedTable } from '@/components/workout/PlannedCompletedTable'
import { StepsBreakdown } from '@/components/workout/StepsBreakdown'

function dateBR(iso: string | undefined): string {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y}`
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 p-2 dark:bg-slate-800/60">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-sm font-semibold text-slate-700 dark:text-slate-100">{value}</div>
    </div>
  )
}

export function WorkoutDetailDrawer({
  planned, completed, onClose,
}: { planned: PlannedWorkout | null; completed: CompletedWorkout | null; onClose: () => void }) {
  const { data: streams } = useWorkoutStreams(completed?.id ?? null)
  const ftp = planned?.structure?.ftp_watts ?? 250
  const segments = structureToSegments(planned?.structure ?? null, ftp)
  const steps = structureToSteps(planned?.structure ?? null, ftp)
  const title = planned?.name ?? completed?.name ?? 'Treino'
  const date = dateBR(completed?.workout_date ?? planned?.planned_date)
  const wtype = completed?.workout_type ?? planned?.workout_type ?? ''

  // Fecha com Esc
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="flex max-h-[94vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl lg:max-w-6xl 2xl:max-w-[90vw] 2xl:w-[90vw] dark:bg-slate-900"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Cabeçalho */}
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-4 dark:border-slate-800">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-bold text-slate-800 dark:text-slate-100">{title}</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {[date, wtype].filter(Boolean).join(' · ')}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar"
            className="shrink-0 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Corpo rolável */}
        <div className="space-y-5 overflow-y-auto px-6 py-5">
          {planned?.adjustment && (
            <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm text-violet-800 dark:border-violet-500/40 dark:bg-violet-500/10 dark:text-violet-300">
              🤖 Treino ajustado pela IA. Valores efetivos refletem o ajuste do dia.
            </div>
          )}

          {/* Gráfico em largura total */}
          <div className="rounded-xl border border-slate-100 p-3 dark:border-slate-800">
            <IntensityProfile segments={segments} streams={streams} ftp={ftp} />
          </div>

          {/* Métricas-chave do executado */}
          {completed && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Metric label="Pot. média" value={completed.avg_power != null ? `${Math.round(completed.avg_power)} W` : '—'} />
              <Metric label="NP" value={completed.normalized_power != null ? `${Math.round(completed.normalized_power)} W` : '—'} />
              <Metric label="FC média" value={completed.avg_hr != null ? `${Math.round(completed.avg_hr)} bpm` : '—'} />
              <Metric label="TSS" value={completed.tss != null ? String(Math.round(completed.tss)) : '—'} />
            </div>
          )}

          {/* Duas colunas: tabela à esquerda, steps/descrição à direita */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">Planejado × Executado</h3>
              <PlannedCompletedTable planned={planned} completed={completed} />
            </div>
            <div className="space-y-4">
              {steps.length > 0 && (
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">Estrutura do treino</h3>
                  <StepsBreakdown steps={steps} />
                </div>
              )}
              {(planned?.description || completed?.notes) && (
                <div>
                  <h3 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-200">Observações</h3>
                  <p className="text-sm text-slate-600 dark:text-slate-300">{planned?.description ?? completed?.notes}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
