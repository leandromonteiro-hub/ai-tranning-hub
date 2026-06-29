"use client";
import { Bike } from 'lucide-react'
import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'
import { cardStatus, statusColor } from '@/lib/compliance'
import { formatDistanceKm, formatDuration, formatTss } from '@/lib/format'
import { structureToSegments } from '@/lib/structure'
import { IntensityThumbnail } from '@/components/calendar/IntensityThumbnail'

export function WorkoutCard({
  planned, completed, onOpen,
}: { planned: PlannedWorkout | null; completed: CompletedWorkout | null; onOpen: (id: string) => void }) {
  const status = cardStatus({ hasCompleted: !!completed, hasAdjustment: !!planned?.adjustment, isRest: false })
  const title = planned?.name ?? completed?.name ?? 'Treino'
  const durationS = completed?.duration_s ?? planned?.planned_duration_s ?? null
  const tss = completed?.tss ?? planned?.planned_tss ?? null
  const openId = completed?.id ?? planned?.id ?? ''
  const segments = structureToSegments(planned?.structure ?? null)

  return (
    <button
      type="button"
      onClick={() => onOpen(openId)}
      className="w-full overflow-hidden rounded-lg border border-slate-200 bg-white text-left shadow-sm transition hover:shadow dark:border-slate-700 dark:bg-slate-900"
    >
      <div style={{ height: 4, background: statusColor(status) }} />
      <div className="space-y-1 p-2">
        <div className="flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-1 text-sm font-semibold text-slate-800 dark:text-slate-100">
            <Bike className="h-3.5 w-3.5 shrink-0 text-violet-500" />
            <span className="truncate">{title}</span>
          </span>
          {planned?.adjustment && <span className="shrink-0 text-xs font-medium text-violet-600 dark:text-violet-400">🤖 IA</span>}
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
          <span>{formatDuration(durationS)}{completed ? ' ✓' : ''}</span>
          {completed?.distance_m != null && <span>{formatDistanceKm(completed.distance_m)}</span>}
          <span className="font-medium">{formatTss(tss)}</span>
        </div>
        {planned?.description && <p className="line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{planned.description}</p>}
        {segments.length > 0 && <IntensityThumbnail segments={segments} />}
      </div>
    </button>
  )
}
