import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CadastroForm } from '@/components/auth/CadastroForm'

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }))
vi.mock('@/components/auth/GoogleSignInButton', () => ({
  GoogleSignInButton: () => <div data-testid="google-signin" />,
}))

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

beforeEach(() => {
  vi.restoreAllMocks()
})

function fill() {
  fireEvent.change(screen.getByLabelText('Nome completo'), { target: { value: 'Ana' } })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'ana@x.com' } })
  fireEvent.change(screen.getByLabelText('Senha (mínimo 8 caracteres)'), { target: { value: 'senha12345' } })
  fireEvent.change(screen.getByLabelText('Código de convite'), { target: { value: 'ABCD2345' } })
}

describe('CadastroForm', () => {
  it('botão desabilitado até preencher tudo', () => {
    render(<CadastroForm />)
    expect(screen.getByRole('button', { name: /Criar conta/ })).toBeDisabled()
    fill()
    expect(screen.getByRole('button', { name: /Criar conta/ })).toBeEnabled()
  })

  it('409 mostra mensagem de email já usado', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonRes({ error: 'dup' }, 409)))
    render(<CadastroForm />)
    fill()
    fireEvent.click(screen.getByRole('button', { name: /Criar conta/ }))
    expect(await screen.findByText('Este email já tem conta — use a página de login.')).toBeInTheDocument()
  })

  it('403 mostra mensagem de convite inválido', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonRes({ error: 'invite_invalid' }, 403)))
    render(<CadastroForm />)
    fill()
    fireEvent.click(screen.getByRole('button', { name: /Criar conta/ }))
    expect(await screen.findByText('Código de convite inválido ou já usado.')).toBeInTheDocument()
  })

  it('renderiza o botão Google', () => {
    render(<CadastroForm />)
    expect(screen.getByTestId('google-signin')).toBeInTheDocument()
  })
})
