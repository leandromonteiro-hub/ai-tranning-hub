import { render, screen, waitFor } from '@testing-library/react'
import { SWRConfig } from 'swr'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AdminView } from '@/components/admin/AdminView'

afterEach(() => vi.restoreAllMocks())

const json = (b: unknown) =>
  new Response(JSON.stringify(b), { status: 200, headers: { 'Content-Type': 'application/json' } })

// cache SWR fresco por render → sem vazamento de dados entre os testes
function renderView() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, errorRetryCount: 0 }}>
      <AdminView />
    </SWRConfig>,
  )
}

describe('AdminView', () => {
  it('mostra métricas, atletas e feedbacks', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      const u = String(url)
      if (u.includes('admin/usage')) return json({ athletes: 2, workouts: 100, recommendations: 5, feedback_count: 3, avg_feedback_rating: 4.2 })
      if (u.includes('admin/athletes')) return json([{ id: '1', full_name: 'Leandro', email: 'l@x.com', role: 'ATHLETE', tenant_id: 't', is_active: true, created_at: '' }])
      if (u.includes('admin/feedback')) return json([{ id: 'f1', recommendation_id: 'r', athlete_id: '1', rating: 5, made_sense: true, observed_result: null, comment: 'top', created_at: '2026-06-29T00:00:00Z' }])
      return json([])
    })
    renderView()
    await waitFor(() => expect(screen.getByText('100')).toBeInTheDocument())
    expect(screen.getByText('l@x.com')).toBeInTheDocument()
    expect(screen.getAllByText('Leandro').length).toBeGreaterThan(0)
    expect(screen.getByText('top')).toBeInTheDocument()
    expect(screen.getByText('4.2')).toBeInTheDocument()
  })

  it('mostra acesso restrito quando a API retorna 403', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      return new Response(JSON.stringify({ error: 'forbidden' }), { status: 403, headers: { 'Content-Type': 'application/json' } })
    })
    renderView()
    await waitFor(() => expect(screen.getByText(/Acesso restrito/)).toBeInTheDocument())
  })
})
