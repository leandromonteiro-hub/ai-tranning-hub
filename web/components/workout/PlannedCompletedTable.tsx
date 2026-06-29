import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'
import { formatDistanceKm, formatDuration } from '@/lib/format'

export function PlannedCompletedTable({ planned, completed }: { planned: PlannedWorkout | null; completed: CompletedWorkout | null }) {
  const num = (v: number | null | undefined, digits = 0) => (v == null ? '—' : v.toFixed(digits))
  const rows: Array<[string, string, string]> = [
    ['Duration', formatDuration(planned?.planned_duration_s ?? null), formatDuration(completed?.duration_s ?? null)],
    ['Distance', '—', formatDistanceKm(completed?.distance_m ?? null)],
    ['TSS', num(planned?.planned_tss), num(completed?.tss)],
    ['IF', '—', num(completed?.intensity_factor ?? null, 2)],
    ['NP', '—', completed?.normalized_power != null ? `${Math.round(completed.normalized_power)} W` : '—'],
    ['Work', '—', completed?.kj != null ? `${Math.round(completed.kj)} kJ` : '—'],
    ['El. Gain', '—', completed?.elevation_gain_m != null ? `${Math.round(completed.elevation_gain_m)} m` : '—'],
  ]
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-slate-400">
          <th className="font-normal"></th><th className="font-normal">Planned</th><th className="font-normal">Completed</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([k, p, c]) => (
          <tr key={k} className="border-t border-slate-100 dark:border-slate-800">
            <td className="py-1 text-slate-500 dark:text-slate-400">{k}</td>
            <td className="py-1 text-slate-700 dark:text-slate-200">{p}</td>
            <td className="py-1 font-medium text-slate-800 dark:text-slate-100">{c}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
