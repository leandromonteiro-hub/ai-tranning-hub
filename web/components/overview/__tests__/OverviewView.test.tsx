import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { OverviewView } from '@/components/overview/OverviewView'
import { useIntelligence, useCalendar, useRecommendations } from '@/lib/hooks'
import { mondayOf } from '@/lib/weekRange'

vi.mock('@/lib/hooks', () => ({
  useIntelligence: vi.fn(),
  useCalendar: vi.fn(),
  useRecommendations: vi.fn(),
}))

const swr = (data: unknown, isLoading = false) => ({ data, error: undefined, isLoading, mutate: vi.fn() })

function setup(over: {
  intel?: unknown; cal?: unknown; recs?: unknown
} = {}) {
  ;(useIntelligence as Mock).mockReturnValue(swr(over.intel))
  ;(useCalendar as Mock).mockReturnValue(swr(over.cal))
  ;(useRecommendations as Mock).mockReturnValue(swr(over.recs))
}

beforeEach(() => vi.clearAllMocks())

describe('OverviewView', () => {
  it('cabeçalho: título e botão gerar recomendação', () => {
    setup()
    render(<OverviewView />)
    expect(screen.getByText('Visão geral')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Gerar recomendação/ })).toHaveAttribute('href', '/recomendacoes')
  })

  it('Forma: mostra TSB e leitura quando há form', () => {
    setup({ intel: { form: { metric_date: '2026-07-07', ctl: 60, atl: 45, tsb: 12 }, ftp_history: [], twin_seed: null } })
    render(<OverviewView />)
    expect(screen.getByText('+12')).toBeInTheDocument()
    expect(screen.getByText(/Fresco/)).toBeInTheDocument()
  })

  it('Forma: estado vazio quando não há form', () => {
    setup({ intel: { form: null, ftp_history: [], twin_seed: null } })
    render(<OverviewView />)
    expect(screen.getByText(/Sem dados de forma/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Importar treinos/ })).toHaveAttribute('href', '/importar')
  })

  it('Próximo treino: mostra o próximo planejado', () => {
    const today = new Date().toISOString().slice(0, 10)
    setup({ cal: { days: [{ date: today, planned: [{
      id: 'x', planned_date: today, name: 'Endurance Z2', workout_type: 'endurance',
      planned_duration_s: 5400, planned_tss: 70, description: null, structure: null, adjustment: null,
    }], completed: [], races: [] }], weeks: [] } })
    render(<OverviewView />)
    expect(screen.getByText('Endurance Z2')).toBeInTheDocument()
  })

  it('Próximo treino: vazio quando não há planejado', () => {
    setup({ cal: { days: [], weeks: [] } })
    render(<OverviewView />)
    expect(screen.getByText(/Nenhum treino planejado/)).toBeInTheDocument()
  })

  it('Semana + recomendação: totais e resumo', () => {
    const today = new Date().toISOString().slice(0, 10)
    setup({
      cal: { days: [], weeks: [{
        week_start: mondayOf(today), ctl: 50, atl: 40, tsb: 10,
        total_duration_s: 7200, total_tss: 123, total_distance_m: 60000, total_elevation_m: 0, total_kj: 0,
      }] },
      recs: [{
        id: 'r', target_date: null, kind: 'daily_workout', summary: 'Endurance longo hoje',
        physiological_objective: null, block_relation: null, rationale: null,
        adjust_if_tired: null, adjust_if_less_time: null, payload: null,
        risk_level: 'LOW', risk_flags: null, confidence: null, confidence_rationale: null,
        decision: 'PENDING', created_at: '2026-07-07T00:00:00Z', evidence: [],
      }],
    })
    render(<OverviewView />)
    expect(screen.getByText(/123/)).toBeInTheDocument()
    expect(screen.getByText(/Endurance longo hoje/)).toBeInTheDocument()
  })
})
