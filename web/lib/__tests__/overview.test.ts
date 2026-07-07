import { describe, expect, it } from 'vitest'
import { addDaysIso, nextPlannedWorkout, currentWeekSummary, mostRecentRec } from '@/lib/overview'
import type { CalendarResponse, Recommendation } from '@/lib/types'

const planned = (id: string, date: string) => ({
  id, planned_date: date, name: `T-${id}`, workout_type: 'endurance',
  planned_duration_s: 3600, planned_tss: 50, description: null, structure: null, adjustment: null,
})
const week = (start: string) => ({
  week_start: start, ctl: 50, atl: 40, tsb: 10,
  total_duration_s: 7200, total_tss: 120, total_distance_m: 60000, total_elevation_m: 500, total_kj: 1800,
})

describe('addDaysIso', () => {
  it('soma dias cruzando mês', () => {
    expect(addDaysIso('2026-07-05', 14)).toBe('2026-07-19')
    expect(addDaysIso('2026-06-25', 10)).toBe('2026-07-05')
  })
})

describe('nextPlannedWorkout', () => {
  const cal: CalendarResponse = {
    days: [
      { date: '2026-07-06', planned: [planned('a', '2026-07-06')], completed: [], races: [] },
      { date: '2026-07-08', planned: [planned('b', '2026-07-08')], completed: [], races: [] },
    ],
    weeks: [],
  }
  it('pega o primeiro planejado com data >= hoje', () => {
    expect(nextPlannedWorkout(cal, '2026-07-07')?.id).toBe('b')
  })
  it('inclui hoje', () => {
    expect(nextPlannedWorkout(cal, '2026-07-06')?.id).toBe('a')
  })
  it('null quando não há futuro', () => {
    expect(nextPlannedWorkout(cal, '2026-07-09')).toBeNull()
    expect(nextPlannedWorkout(undefined, '2026-07-07')).toBeNull()
  })
})

describe('currentWeekSummary', () => {
  const cal: CalendarResponse = { days: [], weeks: [week('2026-07-06'), week('2026-06-29')] }
  it('acha a semana cujo week_start é a segunda de hoje', () => {
    // 2026-07-08 é uma quarta; a segunda da semana é 2026-07-06
    expect(currentWeekSummary(cal, '2026-07-08')?.week_start).toBe('2026-07-06')
  })
  it('null quando não há semana correspondente', () => {
    expect(currentWeekSummary(cal, '2026-08-01')).toBeNull()
    expect(currentWeekSummary(undefined, '2026-07-08')).toBeNull()
  })
})

describe('mostRecentRec', () => {
  const mk = (id: string, created: string): Recommendation => ({
    id, target_date: null, kind: 'daily_workout', summary: `S-${id}`,
    physiological_objective: null, block_relation: null, rationale: null,
    adjust_if_tired: null, adjust_if_less_time: null, payload: null,
    risk_level: 'LOW', risk_flags: null, confidence: null, confidence_rationale: null,
    decision: 'PENDING', created_at: created, evidence: [],
  })
  it('retorna a mais recente por created_at', () => {
    expect(mostRecentRec([mk('a', '2026-07-01T00:00:00Z'), mk('b', '2026-07-05T00:00:00Z')])?.id).toBe('b')
  })
  it('null p/ lista vazia ou undefined', () => {
    expect(mostRecentRec([])).toBeNull()
    expect(mostRecentRec(undefined)).toBeNull()
  })
})
