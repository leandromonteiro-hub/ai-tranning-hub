export type RiskBadge = { label: string; emoji: string; variant: 'success' | 'warning' | 'error' | 'info' }

export function riskBadge(risk: string): RiskBadge {
  switch (risk) {
    case 'LOW': return { label: 'Risco baixo', emoji: '🟢', variant: 'success' }
    case 'MODERATE': return { label: 'Risco moderado', emoji: '🟡', variant: 'warning' }
    case 'HIGH': return { label: 'Risco alto', emoji: '🔴', variant: 'error' }
    default: return { label: risk || '—', emoji: '⚪', variant: 'info' }
  }
}

export type FeedbackStats = { count?: number; avg_rating?: number; made_sense_pct?: number }

/** Linha de transparência "considerou suas últimas N avaliações". '' quando sem feedback. */
export function feedbackLine(stats: FeedbackStats | null | undefined): string {
  if (!stats || !stats.count) return ''
  let s = `📝 Considerou suas últimas ${stats.count} avaliações`
  if (stats.avg_rating != null) s += ` — nota média ponderada ${stats.avg_rating}`
  if (stats.made_sense_pct != null) s += ` · fez sentido ${stats.made_sense_pct}%`
  return s
}

export type RecSignals = {
  form?: { ctl?: number; atl?: number; tsb?: number }
  block?: string
  ftp_watts?: number
  methodology?: string
  feedback?: FeedbackStats
}

export function signalsOf(payload: Record<string, unknown> | null): RecSignals {
  return (payload?.signals as RecSignals) ?? {}
}

export function workoutDescription(payload: Record<string, unknown> | null): string | null {
  const d = payload?.workout_description
  return typeof d === 'string' && d.trim() ? d : null
}

export function hasStructured(payload: Record<string, unknown> | null): boolean {
  return !!payload?.structured_workout
}
