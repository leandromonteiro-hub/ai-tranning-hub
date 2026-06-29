import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ProvasView } from '@/components/provas/ProvasView'

afterEach(() => vi.restoreAllMocks())

describe('ProvasView', () => {
  it('mostra o form e o estado vazio quando não há provas', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    render(<ProvasView />)
    expect(screen.getByText('🏁 Provas-alvo')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Cadastrar prova/ })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/Nenhuma prova cadastrada/)).toBeInTheDocument())
  })
})
