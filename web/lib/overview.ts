import type { CalendarResponse, PlannedWorkout, Recommendation, WeekSummary } from '@/lib/types'
import { mondayOf } from '@/lib/weekRange'

/** Soma n dias a uma data ISO (YYYY-MM-DD), em UTC. */
export function addDaysIso(iso: string, n: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d))
  dt.setUTCDate(dt.getUTCDate() + n)
  return dt.toISOString().slice(0, 10)
}

/** Primeiro treino planejado com data >= hoje (ordena por data). */
export function nextPlannedWorkout(
  cal: CalendarResponse | undefined, todayIso: string,
): PlannedWorkout | null {
  if (!cal) return null
  const future = cal.days
    .flatMap((day) => day.planned)
    .filter((p) => p.planned_date >= todayIso)
    .sort((a, b) => a.planned_date.localeCompare(b.planned_date))
  return future[0] ?? null
}

/** Resumo da semana atual (week_start == segunda de hoje). */
export function currentWeekSummary(
  cal: CalendarResponse | undefined, todayIso: string,
): WeekSummary | null {
  if (!cal) return null
  const monday = mondayOf(todayIso)
  return cal.weeks.find((w) => w.week_start === monday) ?? null
}

/** Recomendação mais recente por created_at. */
export function mostRecentRec(recs: Recommendation[] | undefined): Recommendation | null {
  if (!recs || recs.length === 0) return null
  return [...recs].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
}
