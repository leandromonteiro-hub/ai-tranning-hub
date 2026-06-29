import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'

export type DayPair = { planned: PlannedWorkout | null; completed: CompletedWorkout | null }

/**
 * Pareia planejado↔executado de um dia por POSIÇÃO (índice), não por tipo de
 * treino — a maioria dos dias tem 1 de cada, e os planejados importados do TP
 * vêm como tipo "OTHER", então casar por tipo falharia. Sobras (mais planejados
 * que executados, ou vice-versa) viram pares só-planejado / só-executado.
 */
export function pairDayWorkouts(
  planned: PlannedWorkout[],
  completed: CompletedWorkout[],
): DayPair[] {
  const n = Math.max(planned.length, completed.length)
  const pairs: DayPair[] = []
  for (let i = 0; i < n; i++) {
    pairs.push({ planned: planned[i] ?? null, completed: completed[i] ?? null })
  }
  return pairs
}
