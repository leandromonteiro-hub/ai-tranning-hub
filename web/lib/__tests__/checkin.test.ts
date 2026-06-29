import { describe, expect, it } from 'vitest'
import { recoveryBody, subjectiveBody, type CheckinForm } from '@/lib/checkin'

const base: CheckinForm = {
  sleep_hours: '7', resting_hr: '55', hrv_ms: '', fatigue: 3, soreness: 2,
  mood: 4, motivation: 4, injury_flag: false, comment: '',
}

describe('recoveryBody', () => {
  it('coerce números e hrv vazio → null', () => {
    expect(recoveryBody(base, '2026-06-29')).toEqual({
      metric_date: '2026-06-29', sleep_hours: 7, resting_hr: 55, hrv_ms: null,
    })
  })
  it('hrv informado é mantido', () => {
    expect(recoveryBody({ ...base, hrv_ms: '62' }, '2026-06-29').hrv_ms).toBe(62)
  })
  it('sleep_hours e resting_hr vazios → null', () => {
    expect(recoveryBody({ ...base, sleep_hours: '', resting_hr: '' }, '2026-06-29')).toMatchObject({
      sleep_hours: null, resting_hr: null,
    })
  })
})

describe('subjectiveBody', () => {
  it('passa as escalas e comment vazio → null', () => {
    expect(subjectiveBody(base, '2026-06-29')).toEqual({
      metric_date: '2026-06-29', fatigue: 3, soreness: 2, mood: 4, motivation: 4,
      injury_flag: false, comment: null,
    })
  })
  it('comment preenchido é trimado', () => {
    expect(subjectiveBody({ ...base, comment: '  cansado  ' }, '2026-06-29').comment).toBe('cansado')
  })
})
