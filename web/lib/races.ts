import type { Race } from '@/lib/types'

/** Ordena provas por data (ascendente), sem mutar o array original. */
export function sortRacesByDate(races: Race[]): Race[] {
  return [...races].sort((a, b) => a.race_date.localeCompare(b.race_date))
}

/** Cor do badge por prioridade: A (alvo) → vermelho, B → âmbar, C → azul. */
export function priorityVariant(priority: string): 'error' | 'warning' | 'info' {
  if (priority === 'A') return 'error'
  if (priority === 'B') return 'warning'
  return 'info'
}
