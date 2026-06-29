import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FormCards, IntensitySplit } from '@/components/forma/FormaSections'
import type { FormState } from '@/lib/types'

describe('FormCards', () => {
  it('mostra CTL/ATL/TSB e a leitura por TSB', () => {
    const form: FormState = { metric_date: '2026-06-24', ctl: 85, atl: 84, tsb: -10 }
    render(<FormCards form={form} />)
    expect(screen.getByText('85')).toBeInTheDocument()  // CTL
    expect(screen.getByText('84')).toBeInTheDocument()  // ATL
    expect(screen.getByText('-10')).toBeInTheDocument() // TSB com sinal
    expect(screen.getByText(/Equilibrado/)).toBeInTheDocument()
  })
})

describe('IntensitySplit', () => {
  it('renderiza os percentuais por zona', () => {
    render(<IntensitySplit split={{ label: 'pyramidal', z1_pct: 0.7, z2_pct: 0.27, z3_pct: 0.03 }} />)
    expect(screen.getByText(/Fácil 70%/)).toBeInTheDocument()
    expect(screen.getByText(/Moderado 27%/)).toBeInTheDocument()
    expect(screen.getByText(/Forte 3%/)).toBeInTheDocument()
  })
})
