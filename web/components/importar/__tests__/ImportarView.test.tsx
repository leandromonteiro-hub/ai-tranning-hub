import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ImportarView } from '@/components/importar/ImportarView'

vi.mock('@/components/importar/GarminCard', () => ({
  GarminCard: () => <div data-testid="garmin-card" />,
}))

describe('ImportarView', () => {
  it('renderiza o título e o botão Enviar desabilitado sem arquivos', () => {
    render(<ImportarView />)
    expect(screen.getByText('📥 Importar treinos')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Enviar/ })).toBeDisabled()
  })

  it('renderiza o card de conexão Garmin', () => {
    render(<ImportarView />)
    expect(screen.getByTestId('garmin-card')).toBeInTheDocument()
  })
})
