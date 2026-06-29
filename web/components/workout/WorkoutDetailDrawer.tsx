"use client";
import { X } from 'lucide-react'
import { useWorkoutStreams } from '@/lib/hooks'
import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'
import { structureToSegments, structureToSteps } from '@/lib/structure'
import { IntensityProfile } from '@/components/workout/IntensityProfile'
import { PlannedCompletedTable } from '@/components/workout/PlannedCompletedTable'
import { StepsBreakdown } from '@/components/workout/StepsBreakdown'

export function WorkoutDetailDrawer({
  planned, completed, onClose,
}: { planned: PlannedWorkout | null; completed: CompletedWorkout | null; onClose: () => void }) {
  const { data: streams } = useWorkoutStreams(completed?.id ?? null)
  const ftp = planned?.structure?.ftp_watts ?? 250
  const segments = structureToSegments(planned?.structure ?? null, ftp)
  const steps = structureToSteps(planned?.structure ?? null, ftp)
  const title = planned?.name ?? completed?.name ?? 'Treino'

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <aside
        className="h-full w-full max-w-2xl overflow-y-auto bg-white p-5 shadow-xl dark:bg-slate-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Fechar" className="rounded p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
            <X className="h-5 w-5" />
          </button>
        </div>
        <IntensityProfile segments={segments} streams={streams} ftp={ftp} />
        {planned?.adjustment && (
          <div className="my-3 rounded border border-violet-200 bg-violet-50 p-2 text-sm text-violet-800 dark:border-violet-500/40 dark:bg-violet-500/10 dark:text-violet-300">
            🤖 Treino ajustado pela IA. Valores efetivos refletem o ajuste do dia.
          </div>
        )}
        <div className="my-4"><PlannedCompletedTable planned={planned} completed={completed} /></div>
        {completed && (
          <div className="my-4 grid grid-cols-3 gap-2 text-sm text-slate-700 dark:text-slate-200">
            <div><div className="text-xs text-slate-400">Avg Power</div><div>{completed.avg_power != null ? `${Math.round(completed.avg_power)} W` : '—'}</div></div>
            <div><div className="text-xs text-slate-400">Avg HR</div><div>{completed.avg_hr != null ? `${Math.round(completed.avg_hr)} bpm` : '—'}</div></div>
            <div><div className="text-xs text-slate-400">NP</div><div>{completed.normalized_power != null ? `${Math.round(completed.normalized_power)} W` : '—'}</div></div>
          </div>
        )}
        {steps.length > 0 && (
          <div className="my-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">Workout Details</h3>
            <StepsBreakdown steps={steps} />
          </div>
        )}
        {(planned?.description || completed?.notes) && (
          <p className="my-2 text-sm text-slate-600 dark:text-slate-300">{planned?.description ?? completed?.notes}</p>
        )}
      </aside>
    </div>
  )
}
