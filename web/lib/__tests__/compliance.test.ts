import { describe, expect, it } from 'vitest'
import { cardStatus, statusColor } from '@/lib/compliance'

describe('compliance', () => {
  it('prioridade rest > completed > adjusted > planned', () => {
    expect(cardStatus({ hasCompleted: true, hasAdjustment: true, isRest: true })).toBe('rest')
    expect(cardStatus({ hasCompleted: true, hasAdjustment: true, isRest: false })).toBe('completed')
    expect(cardStatus({ hasCompleted: false, hasAdjustment: true, isRest: false })).toBe('adjusted')
    expect(cardStatus({ hasCompleted: false, hasAdjustment: false, isRest: false })).toBe('planned')
  })
  it('cada status tem cor hex', () => {
    for (const s of ['completed', 'planned', 'adjusted', 'rest'] as const) {
      expect(statusColor(s)).toMatch(/^#/)
    }
  })
})
