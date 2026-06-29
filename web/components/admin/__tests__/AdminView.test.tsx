import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AdminView } from '@/components/admin/AdminView'

afterEach(() => vi.restoreAllMocks())

const json = (b: unknown) =>
  new Response(JSON.stringify(b), { status: 200, headers: { 'Content-Type': 'application/json' } })

describe('AdminView', () => {
  it('mostra métricas, atletas e feedbacks', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      const u = String(url)
      if (u.includes('admin/usage')) return json({ athletes: 2, workouts: 100, recommendations: 5, feedback_count: 3, avg_feedback_rating: 4.2 })
      if (u.includes('admin/athletes')) return json([{ id: '1', full_name: 'Leandro', email: 'l@x.com', role: 'ATHLETE', tenant_id: 't', is_active: true, created_at: '' }])
      if (u.includes('admin/feedback')) return json([{ id: 'f1', recommendation_id: 'r', athlete_id: '1', rating: 5, made_sense: true, observed_result: null, comment: 'top', created_at: '2026-06-29T00:00:00Z' }])
      return json([])
    })
    render(<AdminView />)
    await waitFor(() => expect(screen.getByText('100')).toBeInTheDocument()) // treinos
    expect(screen.getByText('l@x.com')).toBeInTheDocument() // atleta na tabela
    expect(screen.getAllByText('Leandro').length).toBeGreaterThan(0) // nome resolvido no feedback
    expect(screen.getByText('top')).toBeInTheDocument() // comentário do feedback
    expect(screen.getByText('4.2')).toBeInTheDocument() // nota média
  })
})
