import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { GarminCard } from '@/components/importar/GarminCard'
import { useGarminStatus } from '@/lib/hooks'
import { apiFetch } from '@/lib/api'
import type { GarminStatus } from '@/lib/types'

vi.mock('@/lib/hooks', () => ({ useGarminStatus: vi.fn() }))
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

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

describe('GarminCard — conectar e MFA', () => {
  it('DISCONNECTED: botão Conectar só habilita com consentimento e campos', () => {
    mockHook({ data: statusOf({ status: 'DISCONNECTED' }) })
    render(<GarminCard />)
    const btn = screen.getByRole('button', { name: /Conectar/ })
    expect(btn).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Email da conta Garmin'), { target: { value: 'a@b.c' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'pw' } })
    expect(btn).toBeDisabled() // ainda falta o consentimento
    fireEvent.click(screen.getByRole('checkbox'))
    expect(btn).toBeEnabled()
  })

  it('connect com 400 mostra erro inline e não navega', async () => {
    mockHook({ data: statusOf({ status: 'DISCONNECTED' }) })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ detail: 'bad' }, 400))
    render(<GarminCard />)
    fireEvent.change(screen.getByLabelText('Email da conta Garmin'), { target: { value: 'a@b.c' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /Conectar/ }))
    expect(await screen.findByText('Email ou senha da Garmin inválidos.')).toBeInTheDocument()
  })

  it('connect ok revalida o status', async () => {
    const mutate = vi.fn()
    ;(useGarminStatus as Mock).mockReturnValue({
      data: statusOf({ status: 'DISCONNECTED' }), error: undefined, isLoading: false, mutate,
    })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ needs_mfa: false, status: 'CONNECTED' }))
    render(<GarminCard />)
    fireEvent.change(screen.getByLabelText('Email da conta Garmin'), { target: { value: 'a@b.c' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /Conectar/ }))
    await waitFor(() => expect(mutate).toHaveBeenCalled())
    expect(apiFetch).toHaveBeenCalledWith('garmin/connect', expect.objectContaining({ method: 'POST' }))
  })

  it('AWAITING_MFA mostra campo de código e envia para connect/mfa', async () => {
    const mutate = vi.fn()
    ;(useGarminStatus as Mock).mockReturnValue({
      data: statusOf({ status: 'AWAITING_MFA' }), error: undefined, isLoading: false, mutate,
    })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ needs_mfa: false, status: 'CONNECTED' }))
    render(<GarminCard />)
    fireEvent.change(screen.getByLabelText('Código de verificação (MFA)'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirmar código/ }))
    await waitFor(() => expect(mutate).toHaveBeenCalled())
    expect(apiFetch).toHaveBeenCalledWith('garmin/connect/mfa', expect.objectContaining({ method: 'POST' }))
  })

  it('MFA expirado (409) volta ao form de credenciais com aviso', async () => {
    mockHook({ data: statusOf({ status: 'AWAITING_MFA' }) })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ detail: 'MFA expired' }, 409))
    render(<GarminCard />)
    fireEvent.change(screen.getByLabelText('Código de verificação (MFA)'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirmar código/ }))
    expect(await screen.findByText('Tempo esgotado — conecte de novo.')).toBeInTheDocument()
    expect(screen.getByLabelText('Email da conta Garmin')).toBeInTheDocument()
  })

  it('NEEDS_REAUTH mostra badge âmbar, last_error e form sem checkbox', () => {
    mockHook({ data: statusOf({ status: 'NEEDS_REAUTH', needs_reauth: true, last_error: 'token expirou' }) })
    render(<GarminCard />)
    expect(screen.getByText('Reconexão necessária')).toBeInTheDocument()
    expect(screen.getByText(/token expirou/)).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Email da conta Garmin')).toBeInTheDocument()
  })
})

describe('GarminCard — sincronizar e desconectar', () => {
  it('sincronizar agora: SUCCESS revalida e mostra confirmação', async () => {
    const mutate = vi.fn()
    ;(useGarminStatus as Mock).mockReturnValue({
      data: statusOf({ status: 'CONNECTED' }), error: undefined, isLoading: false, mutate,
    })
    ;(apiFetch as Mock).mockImplementation(async (path: string) => {
      if (path === 'garmin/sync') return jsonRes({ task_id: 't1' })
      if (path === 'jobs/t1') return jsonRes({ task_id: 't1', state: 'SUCCESS' })
      throw new Error(`unexpected ${path}`)
    })
    render(<GarminCard />)
    fireEvent.click(screen.getByRole('button', { name: /Sincronizar agora/ }))
    expect(await screen.findByText('Sincronizado ✓')).toBeInTheDocument()
    expect(mutate).toHaveBeenCalled()
  })

  it('sincronizar agora: FAILURE mostra mensagem de falha', async () => {
    mockHook({ data: statusOf({ status: 'CONNECTED' }) })
    ;(apiFetch as Mock).mockImplementation(async (path: string) => {
      if (path === 'garmin/sync') return jsonRes({ task_id: 't1' })
      return jsonRes({ task_id: 't1', state: 'FAILURE' })
    })
    render(<GarminCard />)
    fireEvent.click(screen.getByRole('button', { name: /Sincronizar agora/ }))
    expect(await screen.findByText(/sincronização falhou/)).toBeInTheDocument()
  })

  it('sincronizar agora: task_id null (broker fora) mostra falha', async () => {
    mockHook({ data: statusOf({ status: 'CONNECTED' }) })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ task_id: null }))
    render(<GarminCard />)
    fireEvent.click(screen.getByRole('button', { name: /Sincronizar agora/ }))
    expect(await screen.findByText(/sincronização falhou/)).toBeInTheDocument()
  })

  it('desconectar exige confirmação inline antes do DELETE', async () => {
    const mutate = vi.fn()
    ;(useGarminStatus as Mock).mockReturnValue({
      data: statusOf({ status: 'CONNECTED' }), error: undefined, isLoading: false, mutate,
    })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes(null, 204))
    render(<GarminCard />)
    fireEvent.click(screen.getByRole('button', { name: /Desconectar/ }))
    expect(apiFetch).not.toHaveBeenCalled()
    expect(screen.getByText(/Confirmar desconexão\?/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^Sim$/ }))
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('garmin/disconnect', expect.objectContaining({ method: 'DELETE' })))
    expect(mutate).toHaveBeenCalled()
  })

  it('cancelar desconexão volta aos botões normais sem DELETE', () => {
    mockHook({ data: statusOf({ status: 'CONNECTED' }) })
    render(<GarminCard />)
    fireEvent.click(screen.getByRole('button', { name: /Desconectar/ }))
    fireEvent.click(screen.getByRole('button', { name: /Cancelar/ }))
    expect(apiFetch).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /Sincronizar agora/ })).toBeInTheDocument()
  })

  it('desconectar com erro mantém a confirmação e mostra mensagem', async () => {
    mockHook({ data: statusOf({ status: 'CONNECTED' }) })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ detail: 'boom' }, 500))
    render(<GarminCard />)
    fireEvent.click(screen.getByRole('button', { name: /Desconectar/ }))
    fireEvent.click(screen.getByRole('button', { name: /^Sim$/ }))
    expect(await screen.findByText('Não foi possível desconectar. Tente novamente.')).toBeInTheDocument()
    expect(screen.getByText(/Confirmar desconexão\?/)).toBeInTheDocument()
  })
})
