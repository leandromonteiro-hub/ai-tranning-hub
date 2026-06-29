import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { WeekSummary } from '@/lib/types'
import { SummaryColumn } from '@/components/calendar/SummaryColumn'

const week: WeekSummary = {
  week_start: '2026-05-11', ctl: 12, atl: 45, tsb: -12,
  total_duration_s: 49440, total_tss: 767, total_distance_m: 242000, total_elevation_m: 4572, total_kj: 7240,
}

describe('SummaryColumn', () => {
  it('mostra CTL/ATL/TSB e totais', () => {
    render(<SummaryColumn week={week} />)
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('-12')).toBeInTheDocument()
    expect(screen.getByText(/767/)).toBeInTheDocument()
    expect(screen.getByText(/242/)).toBeInTheDocument()
  })
})
