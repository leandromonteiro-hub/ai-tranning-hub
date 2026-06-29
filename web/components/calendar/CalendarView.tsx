"use client";
import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useCalendar } from '@/lib/hooks'
import { addMonths, firstOfMonth, monthGridRange, monthLabel } from '@/lib/weekRange'
import { CalendarGrid } from '@/components/calendar/CalendarGrid'
import { WorkoutDetailDrawer } from '@/components/workout/WorkoutDetailDrawer'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export function CalendarView() {
  const [ref, setRef] = useState<string>(() => firstOfMonth(todayIso()))
  const [start, end] = monthGridRange(ref)
  const { data, isLoading, error } = useCalendar(start, end)
  const [openId, setOpenId] = useState<string | null>(null)

  const selected = openId && data
    ? data.days.flatMap((d) => [
        ...d.completed.filter((c) => c.id === openId).map((c) => ({
          completed: c, planned: d.planned.find((p) => p.workout_type === c.workout_type) ?? null,
        })),
        ...d.planned.filter((p) => p.id === openId && !d.completed.some((c) => c.id === openId))
          .map((p) => ({ completed: null, planned: p })),
      ])[0] ?? null
    : null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">📅 Plano</h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setRef(firstOfMonth(todayIso()))}
            className="rounded-lg border border-slate-300 px-3 py-1 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Hoje
          </button>
          <button
            type="button"
            aria-label="Mês anterior"
            onClick={() => setRef((r) => addMonths(r, -1))}
            className="rounded-lg border border-slate-300 p-1.5 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="min-w-36 text-center text-sm font-semibold text-slate-700 dark:text-slate-200">
            {monthLabel(ref)}
          </span>
          <button
            type="button"
            aria-label="Próximo mês"
            onClick={() => setRef((r) => addMonths(r, 1))}
            className="rounded-lg border border-slate-300 p-1.5 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {isLoading && <p className="text-sm text-slate-500">Carregando…</p>}
      {error && <p className="text-sm text-red-600">Erro ao carregar o calendário.</p>}
      {data && <CalendarGrid days={data.days} weeks={data.weeks} onOpenWorkout={setOpenId} />}

      {selected && (
        <WorkoutDetailDrawer planned={selected.planned} completed={selected.completed} onClose={() => setOpenId(null)} />
      )}
    </div>
  )
}
