import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ConexoesView } from '@/components/conexoes/ConexoesView'

vi.mock('@/components/importar/GarminCard', () => ({
  GarminCard: () => <div data-testid="garmin-card" />,
}))

describe('ConexoesView', () => {
  it('renderiza o título Conexões', () => {
    render(<ConexoesView />)
    expect(screen.getByText('Conexões')).toBeInTheDocument()
  })

  it('renderiza o card do Garmin', () => {
    render(<ConexoesView />)
    expect(screen.getByTestId('garmin-card')).toBeInTheDocument()
  })
})
