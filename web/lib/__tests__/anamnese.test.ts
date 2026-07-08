import { describe, expect, it } from 'vitest'
import { isAnamneseComplete, missingRequiredFields } from '@/lib/anamnese'
import type { AthleteProfile } from '@/lib/types'

const full: AthleteProfile = {
  id: 'p', athlete_id: 'a',
  birth_date: '1990-01-01', sex: 'M', weight_kg: 70, height_cm: 175,
  max_hr: 185, resting_hr: 50, primary_discipline: 'XCM', years_training: 5,
  notes: null, goals: 'ultra', weekly_hours: 10, weekly_days: 5,
  injury_history: null, medical_conditions: null,
  has_power_meter: true, has_hr_monitor: true,
}

describe('isAnamneseComplete', () => {
  it('true quando os 9 obrigatórios estão preenchidos', () => {
    expect(isAnamneseComplete(full)).toBe(true)
  })
  it('false faltando qualquer obrigatório', () => {
    expect(isAnamneseComplete({ ...full, weekly_hours: null })).toBe(false)
    expect(isAnamneseComplete({ ...full, goals: '' as unknown as string })).toBe(false)
    expect(isAnamneseComplete(null)).toBe(false)
  })
  it('não exige os opcionais (resting_hr, weekly_days, lesões)', () => {
    expect(isAnamneseComplete({ ...full, resting_hr: null, weekly_days: null, injury_history: null })).toBe(true)
  })
})

describe('missingRequiredFields', () => {
  it('lista os rótulos dos que faltam', () => {
    const miss = missingRequiredFields({ ...full, weekly_hours: null, max_hr: null })
    expect(miss).toContain('Horas por semana')
    expect(miss).toContain('FC máxima')
    expect(miss).not.toContain('Peso')
  })
  it('null → todos os obrigatórios', () => {
    expect(missingRequiredFields(null)).toHaveLength(9)
  })
})
