import type { WeekSummary } from '@/lib/types'
import { formatDuration } from '@/lib/format'

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <span className="font-medium text-slate-700 dark:text-slate-200">{value}</span>
    </div>
  )
}

export function SummaryColumn({ week }: { week: WeekSummary }) {
  const n = (v: number | null) => (v == null ? '—' : String(Math.round(v)))
  return (
    <div className="space-y-2 border-l border-slate-200 p-3 dark:border-slate-700">
      <div className="grid grid-cols-3 gap-1 text-center">
        {([['Fitness', week.ctl], ['Fatigue', week.atl], ['Form', week.tsb]] as const).map(([k, v]) => (
          <div key={k}>
            <div className="text-[10px] uppercase tracking-wide text-slate-400">{k}</div>
            <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">{n(v)}</div>
          </div>
        ))}
      </div>
      <Row label="Total Duration" value={formatDuration(week.total_duration_s)} />
      <Row label="Total TSS" value={n(week.total_tss)} />
      <Row label="Distance" value={`${(week.total_distance_m / 1000).toFixed(0)} km`} />
      <Row label="El. Gain" value={`${n(week.total_elevation_m)} m`} />
      <Row label="Work" value={`${n(week.total_kj)} kJ`} />
    </div>
  )
}
