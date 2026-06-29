import { describe, expect, it } from 'vitest'
import { pctToZone, powerToZone, zoneColor } from '@/lib/zones'

describe('zones', () => {
  it('pctToZone limites', () => {
    expect(pctToZone(0.5)).toBe(1)
    expect(pctToZone(0.7)).toBe(2)
    expect(pctToZone(0.85)).toBe(3)
    expect(pctToZone(1.0)).toBe(4)
    expect(pctToZone(1.1)).toBe(5)
    expect(pctToZone(1.3)).toBe(6)
    expect(pctToZone(1.7)).toBe(7)
  })
  it('powerToZone usa o ftp', () => {
    expect(powerToZone(300, 300)).toBe(4)
    expect(powerToZone(150, 300)).toBe(1)
  })
  it('zoneColor é hex', () => {
    expect(zoneColor(4)).toMatch(/^#/)
  })
})
