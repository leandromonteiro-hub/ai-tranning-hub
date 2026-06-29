import { describe, expect, it } from 'vitest'
import {
  currentFtp, formReading, formTone, ftpByPeriod, powerCurve, richnessLabel,
} from '@/lib/formState'
import type { FtpPoint } from '@/lib/types'

describe('formReading / formTone', () => {
  it('lê o TSB por faixa', () => {
    expect(formReading(20)).toMatch(/pico de forma/)
    expect(formReading(8)).toMatch(/Fresco/)
    expect(formReading(-5)).toMatch(/Equilibrado/)
    expect(formReading(-20)).toMatch(/fatigado/)
    expect(formReading(-40)).toMatch(/recuperação/)
  })
  it('tom por faixa', () => {
    expect(formTone(8)).toBe('pos')
    expect(formTone(-5)).toBe('mut')
    expect(formTone(-20)).toBe('warn')
    expect(formTone(-40)).toBe('neg')
  })
})

describe('richnessLabel', () => {
  it('rotula por score', () => {
    expect(richnessLabel(0.9)).toBe('alta')
    expect(richnessLabel(0.5)).toBe('média')
    expect(richnessLabel(0.2)).toBe('baixa')
  })
})

const ftps: FtpPoint[] = [
  { ftp_watts: 250, valid_from: '2026-01-01', valid_to: '2026-03-31', method: 'a' },
  { ftp_watts: 260, valid_from: '2026-01-01', valid_to: null, method: 'b' }, // mesmo período, mais novo
  { ftp_watts: 297, valid_from: '2026-04-01', valid_to: null, method: 'c' },
]

describe('FTP helpers', () => {
  it('currentFtp pega o último', () => {
    expect(currentFtp(ftps)).toBe(297)
    expect(currentFtp([])).toBeNull()
  })
  it('ftpByPeriod colapsa por valid_from (último vence) e ordena', () => {
    const out = ftpByPeriod(ftps)
    expect(out.map((f) => f.valid_from)).toEqual(['2026-01-01', '2026-04-01'])
    expect(out[0].ftp_watts).toBe(260)
  })
})

describe('powerCurve', () => {
  it('usa power_curve_bests, com fallback best_marks', () => {
    expect(powerCurve({ power_curve_bests: { '5 min': 391 } })).toEqual({ '5 min': 391 })
    expect(powerCurve({ best_marks: { '1 min': 538 } })).toEqual({ '1 min': 538 })
    expect(powerCurve(null)).toBeNull()
  })
})
