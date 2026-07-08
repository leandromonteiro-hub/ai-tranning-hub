import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FileUploader } from '@/components/importar/FileUploader'

describe('FileUploader', () => {
  it('renderiza o input de arquivos e o botão Enviar desabilitado sem arquivos', () => {
    render(<FileUploader />)
    expect(screen.getByText(/Enviar arquivos/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Enviar/ })).toBeDisabled()
  })
})
