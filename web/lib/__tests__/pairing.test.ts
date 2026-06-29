import { describe, expect, it } from 'vitest'
import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'
import { pairDayWorkouts } from '@/lib/pairing'

const p = (id: string): PlannedWorkout => ({
  id, planned_date: '2026-06-10', name: 'P', workout_type: 'OTHER',
  planned_duration_s: 3600, planned_tss: 80, description: null, structure: null, adjustment: null,
})
const c = (id: string): CompletedWorkout => ({
  id, workout_date: '2026-06-10', name: 'C', workout_type: 'ENDURANCE',
  duration_s: 3600, distance_m: null, tss: 82, intensity_factor: null, avg_power: null,
  normalized_power: null, avg_hr: null, kj: null, elevation_gain_m: null, notes: null,
})

describe('pairDayWorkouts', () => {
  it('pareia 1 planejado + 1 executado por posição (independe do tipo)', () => {
    const pairs = pairDayWorkouts([p('p1')], [c('c1')])
    expect(pairs).toHaveLength(1)
    expect(pairs[0].planned?.id).toBe('p1')
    expect(pairs[0].completed?.id).toBe('c1')
  })
  it('sobra de executados vira par só-executado', () => {
    const pairs = pairDayWorkouts([p('p1')], [c('c1'), c('c2')])
    expect(pairs).toHaveLength(2)
    expect(pairs[1]).toEqual({ planned: null, completed: expect.objectContaining({ id: 'c2' }) })
  })
  it('vazio → []', () => {
    expect(pairDayWorkouts([], [])).toEqual([])
  })
})
