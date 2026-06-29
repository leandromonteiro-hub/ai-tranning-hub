import type { PlannedWorkout, Recommendation } from '@/lib/types'

/** Pode ajustar com a IA: é planejado, de hoje ou futuro, e ainda sem ajuste. */
export function canAdjust(planned: PlannedWorkout | null, todayIso: string): boolean {
  if (!planned || planned.adjustment) return false
  return planned.planned_date >= todayIso
}

export type AdjustPreview = {
  riskLevel: string
  reason: string | null
  adjustedTss: number | null
  adjustedDurationS: number | null
}

const num = (v: unknown): number | null => (typeof v === 'number' ? v : null)

/** Extrai os campos do preview de ajuste da recomendação (kind=day_adjustment). */
export function adjustPreview(rec: Recommendation): AdjustPreview {
  const p = (rec.payload ?? {}) as Record<string, unknown>
  return {
    riskLevel: rec.risk_level,
    reason: rec.rationale ?? rec.summary ?? null,
    adjustedTss: num(p.adjusted_tss),
    adjustedDurationS: num(p.adjusted_duration_s),
  }
}

/** Motivo legível de um ajuste já persistido (WorkoutPlanned.adjustment.reason). */
export function adjustmentReason(adjustment: Record<string, unknown> | null): string | null {
  const r = adjustment?.reason
  return typeof r === 'string' && r.trim() ? r : null
}
