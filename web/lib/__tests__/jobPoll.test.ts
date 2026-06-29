import { describe, expect, it } from 'vitest'
import { pollDecision } from '@/lib/jobPoll'

describe('pollDecision', () => {
  it('SUCCESS → done', () => expect(pollDecision('SUCCESS', 1, 30)).toBe('done'))
  it('FAILURE → failed', () => expect(pollDecision('FAILURE', 1, 30)).toBe('failed'))
  it('não-terminal no limite → giveup', () => expect(pollDecision('PENDING', 30, 30)).toBe('giveup'))
  it('não-terminal antes do limite → continue', () => expect(pollDecision('STARTED', 5, 30)).toBe('continue'))
})
