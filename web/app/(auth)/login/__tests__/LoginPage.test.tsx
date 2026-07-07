import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LoginPage from '@/app/(auth)/login/page'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }))

let capturedOnCredential: ((c: string) => void) | null = null
vi.mock('@/components/auth/GoogleSignInButton', () => ({
  GoogleSignInButton: ({ onCredential }: { onCredential: (c: string) => void }) => {
    capturedOnCredential = onCredential
    return <div data-testid="google-signin" />
  },
}))

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

beforeEach(() => {
  push.mockClear()
  capturedOnCredential = null
})

describe('LoginPage', () => {
  it('email não vem pré-preenchido e há link Criar conta + botão Google', () => {
    render(<LoginPage />)
    expect((screen.getByLabelText('Email') as HTMLInputElement).value).toBe('')
    expect(screen.getByRole('link', { name: /Criar conta/ })).toHaveAttribute('href', '/cadastro')
    expect(screen.getByTestId('google-signin')).toBeInTheDocument()
  })

  it('google com conta nova (invite_required) redireciona para /cadastro?google=1', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonRes({ error: 'invite_required' }, 403)))
    render(<LoginPage />)
    capturedOnCredential!('tok-google')
    await waitFor(() => expect(push).toHaveBeenCalledWith('/cadastro?google=1'))
  })

  it('google com conta existente entra e navega para /', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonRes({ ok: true, role: 'ATHLETE' })))
    render(<LoginPage />)
    capturedOnCredential!('tok-google')
    await waitFor(() => expect(push).toHaveBeenCalledWith('/'))
  })

  it('admin também vai para / (landing unificada)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonRes({ ok: true, role: 'ADMIN' })))
    render(<LoginPage />)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.c' } })
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: /Entrar/ }))
    await waitFor(() => expect(push).toHaveBeenCalledWith('/'))
  })
})
