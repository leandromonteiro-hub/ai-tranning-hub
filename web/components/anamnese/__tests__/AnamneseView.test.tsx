import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AnamneseView } from '@/components/anamnese/AnamneseView'

afterEach(() => vi.restoreAllMocks())

describe('AnamneseView', () => {
  it('carrega o perfil e prefill os campos', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ id: 'p1', athlete_id: 'a', weight_kg: 72, sex: 'M', has_power_meter: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    render(<AnamneseView />)
    expect(screen.getByText('🩺 Anamnese')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByDisplayValue('72')).toBeInTheDocument())
  })
})
