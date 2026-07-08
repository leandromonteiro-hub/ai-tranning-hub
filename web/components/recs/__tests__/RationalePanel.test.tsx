import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RationalePanel } from '@/components/recs/RecsSections'
import type { Recommendation } from '@/lib/types'

function rec(rationale: string): Recommendation {
  return {
    id: 'r', target_date: null, kind: 'daily_workout', summary: 's',
    physiological_objective: 'Estímulo direcionado', block_relation: 'Bloco BASE',
    rationale, adjust_if_tired: 'Se cansado…', adjust_if_less_time: 'Se menos tempo…',
    payload: null, risk_level: 'LOW', risk_flags: null, confidence: 0.7,
    confidence_rationale: null, decision: 'PENDING', created_at: '2026-07-08T00:00:00Z',
    evidence: [],
  } as Recommendation
}

describe('RationalePanel', () => {
  it('renderiza o Racional em markdown (heading + strong, sem sintaxe crua)', () => {
    render(<RationalePanel rec={rec('## Sessão\nFaça **Z2** hoje')} />)
    expect(screen.getByText('Sessão')).toBeInTheDocument()
    expect(screen.getByText('Z2').tagName).toBe('STRONG')
    // o container do racional não mostra os caracteres crus
    expect(document.body.textContent).not.toContain('## Sessão')
  })
})
