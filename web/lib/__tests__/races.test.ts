import { describe, expect, it } from 'vitest'
import { priorityVariant, sortRacesByDate } from '@/lib/races'
import type { Race } from '@/lib/types'

const race = (id: string, race_date: string, priority = 'A'): Race => ({
  id, athlete_id: 'a', name: id, race_date, discipline: null, priority,
  location: null, distance_km: null, elevation_gain_m: null, notes: null, created_at: '',
})

describe('sortRacesByDate', () => {
  it('ordena ascendente sem mutar', () => {
    const input = [race('c', '2026-07-04'), race('a', '2026-03-01'), race('b', '2026-05-20')]
    const out = sortRacesByDate(input)
    expect(out.map((r) => r.id)).toEqual(['a', 'b', 'c'])
    expect(input.map((r) => r.id)).toEqual(['c', 'a', 'b']) // original intacto
  })
})

describe('priorityVariant', () => {
  it('mapeia prioridade → cor', () => {
    expect(priorityVariant('A')).toBe('error')
    expect(priorityVariant('B')).toBe('warning')
    expect(priorityVariant('C')).toBe('info')
  })
})
