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

  it('botão Gerar plano dispara generate + expand e mostra sucesso', async () => {
    const race = {
      id: 'r1', athlete_id: 'a', name: 'Cape Epic', race_date: '2099-03-21',
      end_date: '2099-03-28', priority: 'A', discipline: null, location: null,
      distance_km: null, elevation_gain_m: null, notes: null, created_at: '',
    }
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
      const u = String(url)
      if (u.endsWith('/plans/generate')) {
        return new Response(JSON.stringify({ id: 'p1' }), { status: 201, headers: { 'Content-Type': 'application/json' } })
      }
      if (u.endsWith('/plans/p1/expand')) {
        return new Response(JSON.stringify({ days: 193, tss_total: 1, start: '', end: '' }), { status: 201, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response(JSON.stringify([race]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <ProvasView />
      </SWRConfig>,
    )
    const btn = await screen.findByRole('button', { name: /Gerar plano/ })
    fireEvent.click(btn)
    await waitFor(() => expect(screen.getByText(/Plano gerado: 193 treinos/)).toBeInTheDocument())
    const urls = spy.mock.calls.map(([u]) => String(u))
    expect(urls.some((u) => u.endsWith('/plans/generate'))).toBe(true)
    expect(urls.some((u) => u.endsWith('/plans/p1/expand'))).toBe(true)
    const genCall = spy.mock.calls.find(([u]) => String(u).endsWith('/plans/generate'))!
    expect(JSON.parse(String(genCall[1]!.body))).toMatchObject({
      name: 'Plano — Cape Epic', race_date: '2099-03-21', target_race_id: 'r1', priority: 'A',
    })
  })

  it('prova passada não mostra o botão', async () => {
    const past = {
      id: 'r2', athlete_id: 'a', name: 'WOS', race_date: '2020-01-01',
      end_date: null, priority: 'B', discipline: null, location: null,
      distance_km: null, elevation_gain_m: null, notes: null, created_at: '',
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([past]), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <ProvasView />
      </SWRConfig>,
    )
    await screen.findByText('WOS')
    expect(screen.queryByRole('button', { name: /Gerar plano/ })).not.toBeInTheDocument()
  })

  it('falha no generate mostra erro na linha', async () => {
    const race = {
      id: 'r3', athlete_id: 'a', name: 'Epic', race_date: '2099-08-29',
      end_date: null, priority: 'B', discipline: null, location: null,
      distance_km: null, elevation_gain_m: null, notes: null, created_at: '',
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      if (String(url).endsWith('/plans/generate')) return new Response('{}', { status: 500 })
      return new Response(JSON.stringify([race]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <ProvasView />
      </SWRConfig>,
    )
    fireEvent.click(await screen.findByRole('button', { name: /Gerar plano/ }))
    await waitFor(() => expect(screen.getByText(/Não foi possível gerar o plano/)).toBeInTheDocument())
  })
})
