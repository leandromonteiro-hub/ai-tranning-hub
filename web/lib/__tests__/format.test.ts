import { describe, expect, it } from 'vitest'
import { formatDistanceKm, formatDuration, formatTss } from '@/lib/format'

describe('format', () => {
  it('duração h:mm:ss', () => {
    expect(formatDuration(6840)).toBe('1:54:00')
    expect(formatDuration(1500)).toBe('0:25:00')
    expect(formatDuration(null)).toBe('—')
  })
  it('distância km', () => {
    expect(formatDistanceKm(30000)).toBe('30.0 km')
    expect(formatDistanceKm(null)).toBe('—')
  })
  it('tss', () => {
    expect(formatTss(82)).toBe('82 TSS')
    expect(formatTss(null)).toBe('—')
  })
})
