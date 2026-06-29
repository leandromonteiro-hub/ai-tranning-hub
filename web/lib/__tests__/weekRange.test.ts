import { describe, expect, it } from 'vitest'
import { addMonths, firstOfMonth, mondayOf, monthGridRange, monthLabel, weekDays } from '@/lib/weekRange'

describe('weekRange', () => {
  it('mondayOf retorna a segunda da semana', () => {
    expect(mondayOf('2026-05-13')).toBe('2026-05-11')
    expect(mondayOf('2026-05-11')).toBe('2026-05-11')
  })
  it('weekDays gera 7 dias Seg→Dom', () => {
    expect(weekDays('2026-05-11')).toEqual([
      '2026-05-11', '2026-05-12', '2026-05-13', '2026-05-14', '2026-05-15', '2026-05-16', '2026-05-17',
    ])
  })
  it('firstOfMonth', () => {
    expect(firstOfMonth('2026-06-29')).toBe('2026-06-01')
  })
  it('addMonths cruza fronteira de ano', () => {
    expect(addMonths('2026-06-01', 1)).toBe('2026-07-01')
    expect(addMonths('2026-01-01', -1)).toBe('2025-12-01')
  })
  it('monthLabel PT-BR', () => {
    expect(monthLabel('2026-06-15')).toBe('Junho 2026')
  })
  it('monthGridRange cobre 6 semanas a partir da segunda que cobre o dia 1', () => {
    // junho/2026: dia 1 é segunda → grade começa 2026-06-01 e termina 41 dias depois
    expect(monthGridRange('2026-06-10')).toEqual(['2026-06-01', '2026-07-12'])
  })
})
