import { describe, expect, it } from 'vitest'
import { median, methodologySummary, type MethodologyTwin } from '@/lib/methodology'

describe('median', () => {
  it('ímpar / par / vazio', () => {
    expect(median([3, 1, 2])).toBe(2)
    expect(median([1, 2, 3, 4])).toBe(2.5)
    expect(median([])).toBeNull()
  })
  it('robusta a outlier', () => {
    expect(median([-8, -10, -11, -95])).toBe(-10.5)
  })
})

describe('methodologySummary', () => {
  it('deriva periodização + medianas dos tapers', () => {
    const twin: MethodologyTwin = {
      periodization_summary: { n_blocks: 39, recovery_blocks: 11, meso_length_days_typical: 10 },
      tapers: [
        { race_date: '2025-08-30', ctl_start: 75.4, ctl_race: 86.9, tsb_race: -11.1, atl_race: 116.4, evidence: '' },
        { race_date: '2026-06-06', ctl_start: 91.7, ctl_race: 87.4, tsb_race: 14.6, atl_race: 92, evidence: '' },
      ],
    }
    const s = methodologySummary(twin)
    expect(s.mesoLengthDays).toBe(10)
    expect(s.recoveryEveryN).toBe(4) // round(39/11)
    expect(s.taperCount).toBe(2)
    expect(s.medianTsbRace).toBeCloseTo(1.75) // mediana(-11.1, 14.6)
    expect(s.medianCtlGain).toBeCloseTo((11.5 + -4.3) / 2, 1) // mediana dos ganhos
  })
  it('twin nulo → tudo vazio', () => {
    const s = methodologySummary(null)
    expect(s).toMatchObject({ mesoLengthDays: null, taperCount: 0, medianTsbRace: null })
  })
})
