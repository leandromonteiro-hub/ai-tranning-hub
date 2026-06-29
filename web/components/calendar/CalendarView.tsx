"use client";
import { useMemo, useState } from 'react'
import { useCalendar } from '@/lib/hooks'
import { mondayOf, weekDays } from '@/lib/weekRange'
import { CalendarGrid } from '@/components/calendar/CalendarGrid'
import { WorkoutDetailDrawer } from '@/components/workout/WorkoutDetailDrawer'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export function CalendarView() {
  const monday = useMemo(() => mondayOf(todayIso()), [])
  const days = useMemo(() => weekDays(monday), [monday])
  const { data, isLoading, error } = useCalendar(days[0], days[6])
  const [openId, setOpenId] = useState<string | null>(null)

  if (isLoading) return <p className="text-sm text-slate-500">Carregando…</p>
  if (error || !data) return <p className="text-sm text-red-600">Erro ao carregar o calendário.</p>

  const selected = openId
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
      <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">📅 Plano — Calendário</h1>
      <CalendarGrid days={data.days} weeks={data.weeks} onOpenWorkout={setOpenId} />
      {selected && (
        <WorkoutDetailDrawer planned={selected.planned} completed={selected.completed} onClose={() => setOpenId(null)} />
      )}
    </div>
  )
}
