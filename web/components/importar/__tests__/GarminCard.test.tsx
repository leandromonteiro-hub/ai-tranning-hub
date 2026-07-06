import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { GarminCard } from '@/components/importar/GarminCard'
import { useGarminStatus } from '@/lib/hooks'
import type { GarminStatus } from '@/lib/types'

vi.mock('@/lib/hooks', () => ({ useGarminStatus: vi.fn() }))
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))

const statusOf = (over: Partial<GarminStatus>): GarminStatus => ({
  status: 'DISCONNECTED', last_sync_at: null, needs_reauth: false, last_error: null, ...over,
})

function mockHook(v: { data?: GarminStatus; error?: unknown; isLoading?: boolean }) {
  ;(useGarminStatus as Mock).mockReturnValue({
    data: v.data, error: v.error, isLoading: v.isLoading ?? false, mutate: vi.fn(),
  })
}

beforeEach(() => vi.clearAllMocks())

describe('GarminCard — estados de leitura', () => {
  it('não renderiza nada quando a feature está desligada (503)', () => {
    mockHook({ error: { status: 503 } })
    const { container } = render(<GarminCard />)
    expect(container).toBeEmptyDOMElement()
  })

  it('não renderiza nada em erro desconhecido de status', () => {
    mockHook({ error: new Error('boom') })
    const { container } = render(<GarminCard />)
    expect(container).toBeEmptyDOMElement()
  })

  it('mostra skeleton enquanto carrega', () => {
    mockHook({ isLoading: true })
    render(<GarminCard />)
    expect(screen.getByTestId('garmin-skeleton')).toBeInTheDocument()
  })

  it('CONNECTED sem sync mostra "nunca"', () => {
    mockHook({ data: statusOf({ status: 'CONNECTED' }) })
    render(<GarminCard />)
    expect(screen.getByText('Conectado')).toBeInTheDocument()
    expect(screen.getByText(/nunca/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Sincronizar agora/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Desconectar/ })).toBeInTheDocument()
  })

  it('CONNECTED com sync recente mostra tempo relativo', () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 3600_000).toISOString()
    mockHook({ data: statusOf({ status: 'CONNECTED', last_sync_at: twoHoursAgo }) })
    render(<GarminCard />)
    expect(screen.getByText(/há 2 h/)).toBeInTheDocument()
  })
})
