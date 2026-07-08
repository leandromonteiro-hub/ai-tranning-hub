import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { ComparativeWorkouts } from '@/components/recs/RecsSections'
import { apiFetch } from '@/lib/api'
import type { Recommendation } from '@/lib/types'

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))

const wo = (name: string) => ({ name, sport: 'cycling', elements: [], ftp_watts: 250 })
function rec(over: Record<string, unknown> = {}): Recommendation {
  return {
    id: 'r1', target_date: null, kind: 'daily_workout', summary: 's',
    physiological_objective: null, block_relation: null, rationale: null,
    adjust_if_tired: null, adjust_if_less_time: null,
    payload: { structured_workout: wo('IA'), workout_description: 'IA desc',
      methodology_workout: wo('Trad'), methodology_workout_description: 'Trad desc', ...over },
    risk_level: 'LOW', risk_flags: null, confidence: null, confidence_rationale: null,
    decision: 'PENDING', created_at: '2026-07-07T00:00:00Z', evidence: [],
  } as Recommendation
}

beforeEach(() => vi.clearAllMocks())

describe('ComparativeWorkouts', () => {
  it('mostra os dois cards quando há treino tradicional', () => {
    render(<ComparativeWorkouts rec={rec()} onChosen={() => {}} />)
    expect(screen.getByText(/Método tradicional/)).toBeInTheDocument()
    expect(screen.getByText(/Recomendação da IA/)).toBeInTheDocument()
    expect(screen.getByText('Trad desc')).toBeInTheDocument()
    expect(screen.getByText('IA desc')).toBeInTheDocument()
  })

  it('sem treino tradicional mostra só um card', () => {
    render(<ComparativeWorkouts rec={rec({ methodology_workout: undefined, methodology_workout_description: undefined })} onChosen={() => {}} />)
    expect(screen.queryByText(/Método tradicional/)).not.toBeInTheDocument()
    expect(screen.getByText(/Treino/)).toBeInTheDocument()
  })

  it('"Usar este" no tradicional posta decision com chosen_variant methodology', async () => {
    ;(apiFetch as Mock).mockResolvedValue({ ok: true, json: async () => ({}) } as Response)
    render(<ComparativeWorkouts rec={rec()} onChosen={() => {}} />)
    fireEvent.click(screen.getAllByRole('button', { name: /Usar este/ })[0])
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
      'recommendations/r1/decision',
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('methodology') }),
    ))
  })

  it('"Usar este" na IA posta decision com chosen_variant ai', async () => {
    ;(apiFetch as Mock).mockResolvedValue({ ok: true, json: async () => ({}) } as Response)
    render(<ComparativeWorkouts rec={rec()} onChosen={() => {}} />)
    fireEvent.click(screen.getAllByRole('button', { name: /Usar este/ })[1])
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
      'recommendations/r1/decision',
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('"chosen_variant":"ai"') }),
    ))
  })

  it('mostra erro e não marca escolhido quando a API falha', async () => {
    ;(apiFetch as Mock).mockResolvedValue({ ok: false, json: async () => ({}) } as Response)
    const onChosen = vi.fn()
    render(<ComparativeWorkouts rec={rec()} onChosen={onChosen} />)
    fireEvent.click(screen.getAllByRole('button', { name: /Usar este/ })[0])
    await waitFor(() => expect(screen.getByText(/Não foi possível registrar/)).toBeInTheDocument())
    expect(onChosen).not.toHaveBeenCalled()
    expect(screen.queryByText('✓ Escolhido')).not.toBeInTheDocument()
  })

  it('após escolher, marca o card escolhido e trava o outro', async () => {
    ;(apiFetch as Mock).mockResolvedValue({ ok: true, json: async () => ({}) } as Response)
    render(<ComparativeWorkouts rec={rec()} onChosen={() => {}} />)
    fireEvent.click(screen.getAllByRole('button', { name: /Usar este/ })[0])
    await waitFor(() => expect(screen.getByText('✓ Escolhido')).toBeInTheDocument())
    expect(screen.getByText('Não escolhido')).toBeInTheDocument()
  })

  it('recomendação já aceita renderiza a variante escolhida travada', () => {
    const decided = { ...rec({ chosen_variant: 'ai' }), decision: 'ACCEPTED' }
    render(<ComparativeWorkouts rec={decided} onChosen={() => {}} />)
    expect(screen.getByText('✓ Escolhido')).toBeInTheDocument()
    expect(screen.getByText('Não escolhido')).toBeInTheDocument()
  })
})
