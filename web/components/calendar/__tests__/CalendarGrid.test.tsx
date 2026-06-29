import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CalendarDay, WeekSummary } from '@/lib/types'
import { CalendarGrid } from '@/components/calendar/CalendarGrid'

const days: CalendarDay[] = [
  { date: '2026-05-12', planned: [{ id: 'p1', planned_date: '2026-05-12', name: 'Z2', workout_type: 'ENDURANCE', planned_duration_s: 3600, planned_tss: 80, description: null, structure: null, adjustment: null }], completed: [], races: [{ id: 'r1', name: 'WOS Canastra', race_date: '2026-05-20', days_until: 8 }] },
]
const weeks: WeekSummary[] = [{ week_start: '2026-05-11', ctl: 12, atl: 45, tsb: -12, total_duration_s: 3600, total_tss: 80, total_distance_m: 0, total_elevation_m: 0, total_kj: 0 }]

describe('CalendarGrid', () => {
  it('renderiza card e marcador de prova', () => {
    render(<CalendarGrid days={days} weeks={weeks} onOpenWorkout={() => {}} />)
    expect(screen.getByText('Z2')).toBeInTheDocument()
    expect(screen.getByText(/WOS Canastra/)).toBeInTheDocument()
    expect(screen.getByText(/8 DAYS/i)).toBeInTheDocument()
  })
})
