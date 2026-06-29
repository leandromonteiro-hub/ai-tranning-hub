import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RiskHeader, SignalsPanel } from '@/components/recs/RecsSections'
import type { Recommendation } from '@/lib/types'

const rec: Recommendation = {
  id: 'r1', target_date: '2026-06-29', kind: 'daily_workout', summary: 'Endurance Z2 90min',
  physiological_objective: null, block_relation: null, rationale: null,
  adjust_if_tired: null, adjust_if_less_time: null,
  payload: { signals: { block: 'BASE', ftp_watts: 297, form: { ctl: 85, atl: 84, tsb: -9 } } },
  risk_level: 'MODERATE', risk_flags: null, confidence: 0.8, confidence_rationale: null,
  decision: 'PENDING', created_at: '2026-06-29T06:00:00Z', evidence: [],
}

describe('RiskHeader', () => {
  it('mostra risco, confiança e summary', () => {
    render(<RiskHeader rec={rec} />)
    expect(screen.getByText(/Risco moderado/)).toBeInTheDocument()
    expect(screen.getByText(/Confiança: 80%/)).toBeInTheDocument()
    expect(screen.getByText('Endurance Z2 90min')).toBeInTheDocument()
  })
})

describe('SignalsPanel', () => {
  it('mostra forma, bloco e FTP', () => {
    render(<SignalsPanel signals={{ block: 'BASE', ftp_watts: 297, form: { ctl: 85, atl: 84, tsb: -9 } }} />)
    expect(screen.getByText('85')).toBeInTheDocument()  // CTL
    expect(screen.getByText('BASE')).toBeInTheDocument()
    expect(screen.getByText('297 W')).toBeInTheDocument()
    expect(screen.getByText(/Equilibrado/)).toBeInTheDocument() // formReading(-9)
  })
})
