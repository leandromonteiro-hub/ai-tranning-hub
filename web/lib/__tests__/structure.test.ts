import { describe, expect, it } from 'vitest'
import { structureToSegments, structureToSteps } from '@/lib/structure'

const struct = {
  name: 'Z2 c/ Z4',
  ftp_watts: 300,
  elements: [
    { intensity: 'warmup', duration_s: 1500, target: { type: 'power_pct_ftp', low: 0.5, high: 0.65 } },
    { count: 2, steps: [
      { intensity: 'active', duration_s: 720, target: { type: 'power_pct_ftp', low: 0.95, high: 1.05 } },
      { intensity: 'rest', duration_s: 600, target: { type: 'power_pct_ftp', low: 0.5, high: 0.6 } },
    ] },
    { intensity: 'cooldown', duration_s: 900, target: { type: 'open' } },
  ],
}

describe('structureToSegments', () => {
  it('expande repeats e resolve watts', () => {
    const segs = structureToSegments(struct)
    expect(segs).toHaveLength(6)
    expect(segs[1]).toMatchObject({ durationS: 720, lowW: 285, highW: 315, zone: 4 })
    expect(segs[5]).toMatchObject({ intensity: 'cooldown', lowW: null, highW: null })
  })
  it('usa ftp fallback quando structure não tem', () => {
    const segs = structureToSegments({ elements: [{ intensity: 'active', duration_s: 60, target: { type: 'power_pct_ftp', low: 1, high: 1 } }] }, 200)
    expect(segs[0].lowW).toBe(200)
  })
})

describe('structureToSteps', () => {
  it('uma linha por step com rótulo', () => {
    const steps = structureToSteps(struct)
    expect(steps[0].label).toBe('Warm up')
    expect(steps).toHaveLength(6)
  })
})
