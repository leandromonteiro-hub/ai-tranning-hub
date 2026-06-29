import { describe, expect, it } from 'vitest'
import { feedbackLine, hasStructured, riskBadge, signalsOf, workoutDescription } from '@/lib/recs'

describe('riskBadge', () => {
  it('mapeia os níveis', () => {
    expect(riskBadge('LOW')).toMatchObject({ variant: 'success', emoji: '🟢' })
    expect(riskBadge('MODERATE').variant).toBe('warning')
    expect(riskBadge('HIGH').variant).toBe('error')
    expect(riskBadge('?').variant).toBe('info')
  })
})

describe('feedbackLine', () => {
  it('monta a linha quando há contagem', () => {
    expect(feedbackLine({ count: 5, avg_rating: 4.2, made_sense_pct: 80 }))
      .toBe('📝 Considerou suas últimas 5 avaliações — nota média ponderada 4.2 · fez sentido 80%')
  })
  it('vazio sem feedback', () => {
    expect(feedbackLine(null)).toBe('')
    expect(feedbackLine({ count: 0 })).toBe('')
  })
})

describe('payload helpers', () => {
  it('signalsOf extrai signals', () => {
    expect(signalsOf({ signals: { block: 'BASE', ftp_watts: 297 } })).toMatchObject({ block: 'BASE', ftp_watts: 297 })
    expect(signalsOf(null)).toEqual({})
  })
  it('workoutDescription só string não vazia', () => {
    expect(workoutDescription({ workout_description: '10min Z2' })).toBe('10min Z2')
    expect(workoutDescription({ workout_description: '  ' })).toBeNull()
    expect(workoutDescription({})).toBeNull()
  })
  it('hasStructured', () => {
    expect(hasStructured({ structured_workout: { name: 'x' } })).toBe(true)
    expect(hasStructured({})).toBe(false)
  })
})
