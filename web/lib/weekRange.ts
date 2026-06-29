function parse(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}
function fmt(date: Date): string {
  return date.toISOString().slice(0, 10)
}
export function mondayOf(iso: string): string {
  const d = parse(iso)
  const dow = (d.getUTCDay() + 6) % 7
  d.setUTCDate(d.getUTCDate() - dow)
  return fmt(d)
}
export function weekDays(mondayIso: string): string[] {
  const start = parse(mondayIso)
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start)
    d.setUTCDate(start.getUTCDate() + i)
    return fmt(d)
  })
}

const MONTHS_PT = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]

/** Primeiro dia do mês de `iso` (YYYY-MM-01). */
export function firstOfMonth(iso: string): string {
  const [y, m] = iso.split('-').map(Number)
  return fmt(new Date(Date.UTC(y, m - 1, 1)))
}

/** Soma `n` meses (mantém dia 1), p/ navegação. */
export function addMonths(iso: string, n: number): string {
  const [y, m] = iso.split('-').map(Number)
  return fmt(new Date(Date.UTC(y, m - 1 + n, 1)))
}

/** Rótulo PT-BR do mês, ex.: "Junho 2026". */
export function monthLabel(iso: string): string {
  const [y, m] = iso.split('-').map(Number)
  return `${MONTHS_PT[m - 1]} ${y}`
}

/** Mês (YYYY-MM-01) da data mais recente da lista, ou null se vazia. */
export function latestMonth(isoDates: string[]): string | null {
  if (isoDates.length === 0) return null
  const max = isoDates.reduce((mx, d) => (d > mx ? d : mx), isoDates[0])
  return firstOfMonth(max)
}

/** Janela da grade do mês: 6 semanas (42 dias) a partir da segunda que cobre o dia 1. */
export function monthGridRange(iso: string): [string, string] {
  const gridStart = mondayOf(firstOfMonth(iso))
  const start = parse(gridStart)
  const end = new Date(start)
  end.setUTCDate(start.getUTCDate() + 41)
  return [gridStart, fmt(end)]
}
