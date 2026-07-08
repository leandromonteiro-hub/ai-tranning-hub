import { describe, expect, it } from 'vitest'
import { fromProfile, toProfilePayload, isAnamneseComplete, missingRequiredFields, type AnamneseForm } from '@/lib/anamnese'
import type { AthleteProfile } from '@/lib/types'

const empty: AnamneseForm = {
  birth_date: '', sex: '', weight_kg: '', height_cm: '', max_hr: '', resting_hr: '',
  primary_discipline: '', years_training: '', goals: '', weekly_hours: '', weekly_days: '',
  injury_history: '', medical_conditions: '', has_power_meter: false, has_hr_monitor: false,
}

describe('toProfilePayload', () => {
  it('vazios → null e números coeridos', () => {
    const out = toProfilePayload({ ...empty, weight_kg: '72.5', max_hr: '185', has_power_meter: true })
    expect(out.weight_kg).toBe(72.5)
    expect(out.max_hr).toBe(185)
    expect(out.primary_discipline).toBeNull()
    expect(out.goals).toBeNull()
    expect(out.has_power_meter).toBe(true)
    expect(out.has_hr_monitor).toBe(false)
  })
})

describe('fromProfile', () => {
  it('null → formulário vazio', () => {
    expect(fromProfile(null)).toEqual(empty)
  })
  it('perfil → strings (números viram string)', () => {
    const p = { weight_kg: 70, max_hr: 188, sex: 'M', has_hr_monitor: true } as AthleteProfile
    const f = fromProfile(p)
    expect(f.weight_kg).toBe('70')
    expect(f.max_hr).toBe('188')
    expect(f.sex).toBe('M')
    expect(f.has_hr_monitor).toBe(true)
  })
})

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
