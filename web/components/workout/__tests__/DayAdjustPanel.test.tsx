import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DayAdjustPanel } from '@/components/workout/DayAdjustPanel'
import type { PlannedWorkout } from '@/lib/types'

afterEach(() => vi.restoreAllMocks())

const planned = (over: Partial<PlannedWorkout> = {}): PlannedWorkout => ({
  id: 'p1', planned_date: '2099-01-01', name: 'Z2', workout_type: 'ENDURANCE',
  planned_duration_s: 3600, planned_tss: 80, description: null, structure: null, adjustment: null, ...over,
})

const json = (b: unknown) =>
  new Response(JSON.stringify(b), { status: 200, headers: { 'Content-Type': 'application/json' } })

describe('DayAdjustPanel', () => {
  it('mostra "Ajustar com a IA" para treino futuro sem ajuste', () => {
    render(<DayAdjustPanel planned={planned()} onChanged={() => {}} />)
    expect(screen.getByRole('button', { name: /Ajustar com a IA/ })).toBeInTheDocument()
  })

  it('mostra motivo + "Reverter ajuste" quando já ajustado', () => {
    render(<DayAdjustPanel planned={planned({ adjustment: { reason: 'recovery 32 TSS' } })} onChanged={() => {}} />)
    expect(screen.getByText(/recovery 32 TSS/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reverter ajuste/ })).toBeInTheDocument()
  })

  it('gera preview e aceitar chama onChanged', async () => {
    const onChanged = vi.fn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      const u = String(url)
      if (u.includes('apply-adjustment')) return json({})
      if (u.includes('/adjust')) return json({ id: 'rec1', risk_level: 'HIGH', rationale: 'Recovery hoje', payload: { adjusted_tss: 32, adjusted_duration_s: 1800 } })
      return json({})
    })
    render(<DayAdjustPanel planned={planned()} onChanged={onChanged} />)
    await userEvent.click(screen.getByRole('button', { name: /Ajustar com a IA/ }))
    await waitFor(() => expect(screen.getByText(/Ajuste sugerido/)).toBeInTheDocument())
    expect(screen.getByText(/Recovery hoje/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Aceitar ajuste/ }))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
  })
})
