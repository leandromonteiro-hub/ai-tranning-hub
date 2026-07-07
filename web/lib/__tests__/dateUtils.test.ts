import { afterEach, describe, expect, it, vi } from 'vitest'
import { todayIso } from '@/lib/dateUtils'

afterEach(() => vi.useRealTimers())

describe('todayIso', () => {
  it('retorna a data LOCAL (não UTC) no formato YYYY-MM-DD', () => {
    // Instante em que UTC e o horário do Brasil (UTC-3) caem em dias diferentes:
    // 2026-07-07T02:30Z é ainda 2026-07-06 23:30 no fuso local -3.
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-07T02:30:00Z'))
    const d = new Date()
    const expected = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    // A função deve casar com os getters LOCAIS, não com toISOString (UTC).
    expect(todayIso()).toBe(expected)
    expect(todayIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
