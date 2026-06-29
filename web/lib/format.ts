export function formatDuration(s: number | null): string {
  if (s == null) return '—'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}
export function formatDistanceKm(m: number | null): string {
  if (m == null) return '—'
  return `${(m / 1000).toFixed(1)} km`
}
export function formatTss(n: number | null): string {
  if (n == null) return '—'
  return `${Math.round(n)} TSS`
}
