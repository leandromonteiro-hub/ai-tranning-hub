import { describe, expect, it } from 'vitest'
import { endDateFromDays, isFutureRace, priorityVariant, racePeriodLabel, showRaceFlag, sortRacesByDate } from '@/lib/races'
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

describe('endDateFromDays', () => {
  it('1 dia → null (prova de um dia não envia end_date)', () => {
    expect(endDateFromDays('2026-09-12', 1)).toBeNull()
  })
  it('3 dias → dois dias depois', () => {
    expect(endDateFromDays('2026-09-12', 3)).toBe('2026-09-14')
  })
  it('cruza fim de mês', () => {
    expect(endDateFromDays('2026-09-30', 2)).toBe('2026-10-01')
  })
})

describe('racePeriodLabel', () => {
  it('um dia mostra só a data', () => {
    expect(racePeriodLabel({ race_date: '2026-09-12', end_date: null })).toBe('2026-09-12')
  })
  it('multi-dia mostra o período', () => {
    expect(racePeriodLabel({ race_date: '2026-09-12', end_date: '2026-09-14' })).toBe('2026-09-12 – 2026-09-14')
  })
})

describe('showRaceFlag', () => {
  it('esconde prova a mais de 30 dias', () => {
    expect(showRaceFlag(31)).toBe(false)
    expect(showRaceFlag(60)).toBe(false)
  })
  it('mostra a 30 dias ou menos, incluindo durante a prova', () => {
    expect(showRaceFlag(30)).toBe(true)
    expect(showRaceFlag(1)).toBe(true)
    expect(showRaceFlag(0)).toBe(true)
    expect(showRaceFlag(-2)).toBe(true)
  })
})

describe('isFutureRace', () => {
  it('prova de amanhã é futura; de ontem não é', () => {
    expect(isFutureRace({ race_date: '2026-08-03', end_date: null }, '2026-08-02')).toBe(true)
    expect(isFutureRace({ race_date: '2026-08-01', end_date: null }, '2026-08-02')).toBe(false)
  })
  it('prova multi-dia em andamento ainda conta como futura', () => {
    expect(isFutureRace({ race_date: '2026-08-01', end_date: '2026-08-03' }, '2026-08-02')).toBe(true)
  })
})
