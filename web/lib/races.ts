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

/** Converte "Dias" do formulário em end_date ISO; 1 dia → null (não envia). */
export function endDateFromDays(raceDate: string, days: number): string | null {
  if (!raceDate || days <= 1) return null
  const d = new Date(`${raceDate}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days - 1)
  return d.toISOString().slice(0, 10)
}

/** Rótulo da coluna Data: "2026-09-12" ou "2026-09-12 – 2026-09-14". */
export function racePeriodLabel(race: { race_date: string; end_date?: string | null }): string {
  return race.end_date ? `${race.race_date} – ${race.end_date}` : race.race_date
}
