import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StepsBreakdown } from '@/components/workout/StepsBreakdown'

describe('StepsBreakdown', () => {
  it('renderiza rótulo, minutos, watts e zona', () => {
    render(<StepsBreakdown steps={[{ label: 'Warm up', durationS: 1500, lowW: 158, highW: 205, zone: 2 }]} />)
    expect(screen.getByText(/Warm up/)).toBeInTheDocument()
    expect(screen.getByText(/25 min/)).toBeInTheDocument()
    expect(screen.getByText(/158–205 W/)).toBeInTheDocument()
    expect(screen.getByText(/Zona 2/)).toBeInTheDocument()
  })
})
