import { describe, expect, it } from 'vitest'
import { adjustPreview, adjustmentReason, canAdjust } from '@/lib/dayAdjust'
import type { PlannedWorkout, Recommendation } from '@/lib/types'

const planned = (over: Partial<PlannedWorkout> = {}): PlannedWorkout => ({
  id: 'p1', planned_date: '2026-06-29', name: 'Z2', workout_type: 'ENDURANCE',
  planned_duration_s: 3600, planned_tss: 80, description: null, structure: null, adjustment: null, ...over,
})

describe('canAdjust', () => {
  it('hoje/futuro sem ajuste → true', () => {
    expect(canAdjust(planned({ planned_date: '2026-06-29' }), '2026-06-29')).toBe(true)
    expect(canAdjust(planned({ planned_date: '2026-07-10' }), '2026-06-29')).toBe(true)
  })
  it('passado → false', () => {
    expect(canAdjust(planned({ planned_date: '2026-06-20' }), '2026-06-29')).toBe(false)
  })
  it('já ajustado ou nulo → false', () => {
    expect(canAdjust(planned({ adjustment: { reason: 'x' } }), '2026-06-29')).toBe(false)
    expect(canAdjust(null, '2026-06-29')).toBe(false)
  })
})

describe('adjustPreview', () => {
  it('extrai risco, motivo e valores ajustados', () => {
    const rec = {
      id: 'r1', risk_level: 'HIGH', rationale: 'Muito fatigado — recovery',
      payload: { adjusted_tss: 32, adjusted_duration_s: 1800 },
    } as unknown as Recommendation
    expect(adjustPreview(rec)).toEqual({
      riskLevel: 'HIGH', reason: 'Muito fatigado — recovery', adjustedTss: 32, adjustedDurationS: 1800,
    })
  })
})

describe('adjustmentReason', () => {
  it('lê reason do override; vazio → null', () => {
    expect(adjustmentReason({ reason: 'recovery 32 TSS' })).toBe('recovery 32 TSS')
    expect(adjustmentReason({ reason: '  ' })).toBeNull()
    expect(adjustmentReason(null)).toBeNull()
  })
})
