import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SWRConfig } from 'swr'
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

  it('envia end_date calculado a partir do campo Dias', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    render(<ProvasView />)
    fireEvent.change(screen.getByLabelText(/Nome da prova/), { target: { value: 'Brasil Ride' } })
    fireEvent.change(screen.getByLabelText(/^Data$/), { target: { value: '2026-09-12' } })
    fireEvent.change(screen.getByLabelText(/Dias/), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: /Cadastrar prova/ }))
    await waitFor(() => {
      const post = spy.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(post).toBeTruthy()
      expect(JSON.parse(String(post![1]!.body))).toMatchObject({ end_date: '2026-09-14' })
    })
  })

  it('Dias = 1 não envia end_date', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    render(<ProvasView />)
    fireEvent.change(screen.getByLabelText(/Nome da prova/), { target: { value: 'XCO Local' } })
    fireEvent.change(screen.getByLabelText(/^Data$/), { target: { value: '2026-09-12' } })
    fireEvent.click(screen.getByRole('button', { name: /Cadastrar prova/ }))
    await waitFor(() => {
      const post = spy.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(post).toBeTruthy()
      expect(JSON.parse(String(post![1]!.body))).toMatchObject({ end_date: null })
    })
  })

  it('tabela mostra o período quando end_date existe', async () => {
    const race = {
      id: 'r1', athlete_id: 'a', name: 'Brasil Ride', race_date: '2026-09-12',
      end_date: '2026-09-14', priority: 'A', discipline: 'XCM', location: null,
      distance_km: null, elevation_gain_m: null, notes: null, created_at: '2026-08-02T00:00:00Z',
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([race]), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    // Cache SWR novo: os testes anteriores deixaram "races" = [] em cache.
    render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <ProvasView />
      </SWRConfig>,
    )
    await waitFor(() => expect(screen.getByText('2026-09-12 – 2026-09-14')).toBeInTheDocument())
  })
})
