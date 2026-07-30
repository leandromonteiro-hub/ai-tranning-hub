/**
 * O card some quando a integração está desligada, e o erro de limite de membros
 * precisa dizer o que é: a Whoop recusa o 11º atleta enquanto o app não for
 * aprovado, e um "falha ao conectar" genérico manda o operador depurar às cegas.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { WhoopCard } from '@/components/conexoes/WhoopCard'
import { useWhoopStatus } from '@/lib/hooks'
import { useSearchParams } from 'next/navigation'
import { apiFetch } from '@/lib/api'
import type { WhoopStatus } from '@/lib/types'

vi.mock('@/lib/hooks', () => ({ useWhoopStatus: vi.fn() }))
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))
vi.mock('next/navigation', () => ({ useSearchParams: vi.fn() }))

const mockParams = (qs: string) =>
  (useSearchParams as Mock).mockReturnValue(new URLSearchParams(qs))

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

const statusOf = (over: Partial<WhoopStatus>): WhoopStatus => ({
  status: 'DISCONNECTED', last_sync_at: null, last_error: null, connected_at: null, ...over,
})

function mockHook(v: { data?: WhoopStatus; error?: unknown; isLoading?: boolean }) {
  ;(useWhoopStatus as Mock).mockReturnValue({
    data: v.data, error: v.error, isLoading: v.isLoading ?? false, mutate: vi.fn(),
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  mockParams('')
})

describe('WhoopCard', () => {
  it('não renderiza nada quando a feature está desligada (503)', () => {
    mockHook({ error: { status: 503 } })
    const { container } = render(<WhoopCard />)
    expect(container).toBeEmptyDOMElement()
  })

  it('mostra Conectar quando desconectado', () => {
    mockHook({ data: statusOf({ status: 'DISCONNECTED' }) })
    render(<WhoopCard />)
    expect(screen.getByRole('button', { name: /conectar/i })).toBeInTheDocument()
  })

  it('mostra Reconectar quando o token caiu', () => {
    mockHook({ data: statusOf({ status: 'NEEDS_REAUTH' }) })
    render(<WhoopCard />)
    expect(screen.getByRole('button', { name: /reconectar/i })).toBeInTheDocument()
  })

  it('mostra Sincronizar agora quando conectado', () => {
    mockHook({ data: statusOf({ status: 'CONNECTED', connected_at: '2026-07-29T12:00:00Z' }) })
    render(<WhoopCard />)
    expect(screen.getByRole('button', { name: /sincronizar agora/i })).toBeInTheDocument()
  })

  it('explica o limite de membros quando o callback volta com erro', () => {
    // Este é o caminho REAL do 11º atleta: o erro acontece no callback do OAuth,
    // volta na query string, e o card precisa lê-lo. O teste anterior mockava a
    // chamada de authorize, que nunca produz esse detail — passava sem provar nada.
    mockParams('whoop=erro&motivo=whoop_authorization_failed')
    mockHook({ data: statusOf({ status: 'DISCONNECTED' }) })

    render(<WhoopCard />)

    expect(screen.getByText(/limita 10 atletas/i)).toBeInTheDocument()
  })

  it('mostra motivo genérico para um erro desconhecido do callback', () => {
    mockParams('whoop=erro&motivo=coisa_que_nao_mapeamos')
    mockHook({ data: statusOf({ status: 'DISCONNECTED' }) })

    render(<WhoopCard />)

    expect(screen.getByText(/não foi possível concluir/i)).toBeInTheDocument()
  })

  it('não mostra erro quando o callback voltou com sucesso', () => {
    mockParams('whoop=ok')
    mockHook({ data: statusOf({ status: 'CONNECTED' }) })

    render(<WhoopCard />)

    expect(screen.queryByText(/não foi possível/i)).not.toBeInTheDocument()
  })

  it('mostra o erro quando a própria chamada de autorizar falha', async () => {
    mockHook({ data: statusOf({ status: 'DISCONNECTED' }) })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ detail: 'whoop_unavailable' }, 502))
    render(<WhoopCard />)

    fireEvent.click(screen.getByRole('button', { name: /conectar/i }))

    await waitFor(() =>
      expect(screen.getByText(/não respondeu/i)).toBeInTheDocument(),
    )
  })

  it('mostra o motivo quando a conexão caiu', () => {
    mockHook({
      data: statusOf({ status: 'NEEDS_REAUTH', last_error: 'refresh token revogado' }),
    })
    render(<WhoopCard />)
    expect(screen.getByText(/refresh token revogado/i)).toBeInTheDocument()
  })
})
