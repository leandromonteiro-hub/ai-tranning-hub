import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MethodologyView } from '@/components/methodology/MethodologyView'

afterEach(() => vi.restoreAllMocks())

describe('MethodologyView', () => {
  it('mostra periodização, taper, intensidade e termos', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          twin_seed: {
            periodization_summary: { n_blocks: 39, recovery_blocks: 11, meso_length_days_typical: 10 },
            tapers: [{ race_date: '2026-06-06', ctl_start: 91.7, ctl_race: 87.4, tsb_race: 14.6, atl_race: 92, evidence: 'CTL 91→87' }],
            intensity_split: { label: 'pyramidal', z1_pct: 0.7, z2_pct: 0.27, z3_pct: 0.03 },
            coach_terms: [['programado', 25], ['ritmo', 24]],
          },
          ftp_history: [], form: null,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    render(<MethodologyView />)
    await waitFor(() => expect(screen.getByText(/~10 dias/)).toBeInTheDocument())
    expect(screen.getByText(/pyramidal/)).toBeInTheDocument()
    expect(screen.getByText(/programado/)).toBeInTheDocument()
    expect(screen.getByText('2026-06-06')).toBeInTheDocument()
    expect(screen.getByText(/a cada ~4 blocos/)).toBeInTheDocument()
  })
})
