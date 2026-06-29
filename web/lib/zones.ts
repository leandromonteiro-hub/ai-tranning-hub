export function pctToZone(pct: number): number {
  if (pct <= 0.55) return 1
  if (pct <= 0.75) return 2
  if (pct <= 0.9) return 3
  if (pct <= 1.05) return 4
  if (pct <= 1.2) return 5
  if (pct <= 1.5) return 6
  return 7
}
export function powerToZone(watts: number, ftp: number): number {
  if (!ftp || ftp <= 0) return 1
  return pctToZone(watts / ftp)
}
export const ZONE_COLORS: Record<number, string> = {
  1: '#9ca3af', 2: '#3b82f6', 3: '#22c55e', 4: '#eab308', 5: '#f97316', 6: '#ef4444', 7: '#7c3aed',
}
export function zoneColor(zone: number): string {
  return ZONE_COLORS[zone] ?? ZONE_COLORS[1]
}
