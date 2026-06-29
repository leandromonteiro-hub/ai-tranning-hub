import { describe, expect, it } from 'vitest'
import { mondayOf, weekDays } from '@/lib/weekRange'

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
})
