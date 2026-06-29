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
