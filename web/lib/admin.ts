import type { Athlete } from '@/lib/types'

/** Mapa id→nome do atleta, para resolver o athlete_id dos feedbacks. */
export function nameById(athletes: Athlete[]): Record<string, string> {
  const m: Record<string, string> = {}
  for (const a of athletes) m[a.id] = a.full_name
  return m
}
