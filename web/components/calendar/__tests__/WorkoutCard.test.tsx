import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'
import { WorkoutCard } from '@/components/calendar/WorkoutCard'

const planned: PlannedWorkout = {
  id: 'p1', planned_date: '2026-05-12', name: 'Z2 c/ Z4', workout_type: 'ENDURANCE',
  planned_duration_s: 6840, planned_tss: 103, description: 'Z2 com blocos de Z4',
  structure: { ftp_watts: 300, elements: [{ intensity: 'active', duration_s: 600, target: { type: 'power_pct_ftp', low: 1, high: 1 } }] },
  adjustment: null,
}
const completed: CompletedWorkout = {
  id: 'c1', workout_date: '2026-05-12', name: 'Z2 feito', workout_type: 'ENDURANCE',
  duration_s: 6800, distance_m: 51400, tss: 103, intensity_factor: 0.74, avg_power: 210,
  normalized_power: 222, avg_hr: 140, kj: 1434, elevation_gain_m: 300, notes: null,
}

describe('WorkoutCard', () => {
  it('mostra título, tss e duração; onOpen com id do executado', async () => {
    const onOpen = vi.fn()
    render(<WorkoutCard planned={planned} completed={completed} onOpen={onOpen} />)
    expect(screen.getByText('Z2 c/ Z4')).toBeInTheDocument()
    expect(screen.getByText('103 TSS')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button'))
    expect(onOpen).toHaveBeenCalledWith('c1')
  })
  it('badge IA quando há adjustment', () => {
    render(<WorkoutCard planned={{ ...planned, adjustment: { reason: 'x' } }} completed={null} onOpen={() => {}} />)
    expect(screen.getByText('🤖 IA')).toBeInTheDocument()
  })
})
