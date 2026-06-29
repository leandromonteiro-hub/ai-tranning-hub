import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ImportarView } from '@/components/importar/ImportarView'

describe('ImportarView', () => {
  it('renderiza o título e o botão Enviar desabilitado sem arquivos', () => {
    render(<ImportarView />)
    expect(screen.getByText('📥 Importar treinos')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Enviar/ })).toBeDisabled()
  })
})
