"use client";
import { Flag } from 'lucide-react'
import type { CalendarDay, WeekSummary } from '@/lib/types'
import { SummaryColumn } from '@/components/calendar/SummaryColumn'
import { WorkoutCard } from '@/components/calendar/WorkoutCard'
import { mondayOf, weekDays } from '@/lib/weekRange'

const DOW = ['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB', 'DOM']

function RaceFlag({ name, daysUntil }: { name: string; daysUntil: number }) {
  return (
    <div className="rounded border border-blue-300 bg-blue-50 p-1 text-xs text-blue-800 dark:border-blue-500/40 dark:bg-blue-500/10 dark:text-blue-300">
      <div className="font-semibold">{daysUntil} DAYS UNTIL EVENT</div>
      <div className="flex items-center gap-1 truncate"><Flag className="h-3 w-3" />{name}</div>
    </div>
  )
}

export function CalendarGrid({
  days, weeks, onOpenWorkout,
}: { days: CalendarDay[]; weeks: WeekSummary[]; onOpenWorkout: (id: string) => void }) {
  const byDate = new Map(days.map((d) => [d.date, d]))
  const mondays = [...new Set(days.map((d) => mondayOf(d.date)))].sort()
  const weekByStart = new Map(weeks.map((w) => [w.week_start, w]))

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[repeat(7,minmax(0,1fr))_220px] gap-2 text-[11px] font-semibold text-slate-400">
        {DOW.map((d) => <div key={d}>{d}</div>)}
        <div>SUMMARY</div>
      </div>
      {mondays.map((monday) => (
        <div key={monday} className="grid grid-cols-[repeat(7,minmax(0,1fr))_220px] gap-2">
          {weekDays(monday).map((iso) => {
            const day = byDate.get(iso)
            return (
              <div key={iso} className="min-h-32 min-w-0 space-y-1 rounded bg-slate-100/50 p-1 dark:bg-slate-800/40">
                <div className="text-[11px] text-slate-400">{Number(iso.slice(8, 10))}</div>
                {day?.races.map((r) => <RaceFlag key={r.id} name={r.name} daysUntil={r.days_until} />)}
                {day?.planned.map((p) => (
                  <WorkoutCard key={p.id} planned={p}
                    completed={day.completed.find((c) => c.workout_type === p.workout_type) ?? null}
                    onOpen={onOpenWorkout} />
                ))}
                {day?.completed
                  .filter((c) => !day.planned.some((p) => p.workout_type === c.workout_type))
                  .map((c) => <WorkoutCard key={c.id} planned={null} completed={c} onOpen={onOpenWorkout} />)}
              </div>
            )
          })}
          {weekByStart.get(monday)
            ? <SummaryColumn week={weekByStart.get(monday)!} />
            : <div className="border-l border-slate-200 dark:border-slate-700" />}
        </div>
      ))}
    </div>
  )
}
