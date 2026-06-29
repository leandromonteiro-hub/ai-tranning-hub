import { describe, expect, it } from 'vitest'
import { fromProfile, toProfilePayload, type AnamneseForm } from '@/lib/anamnese'
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
