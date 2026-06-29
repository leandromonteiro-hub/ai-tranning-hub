import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CompletedWorkout, PlannedWorkout } from '@/lib/types'
import { PlannedCompletedTable } from '@/components/workout/PlannedCompletedTable'

const planned = { planned_duration_s: 6840, planned_tss: 103 } as PlannedWorkout
const completed = { duration_s: 6800, tss: 103, intensity_factor: 0.74, normalized_power: 222, kj: 1434, distance_m: 51400, elevation_gain_m: 300 } as CompletedWorkout

describe('PlannedCompletedTable', () => {
  it('mostra colunas planejado e executado', () => {
    render(<PlannedCompletedTable planned={planned} completed={completed} />)
    expect(screen.getByText('Planned')).toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.getByText('1:54:00')).toBeInTheDocument()
    expect(screen.getByText('0.74')).toBeInTheDocument()
  })
})
