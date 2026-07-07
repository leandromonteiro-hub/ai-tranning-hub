import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { OnboardingWizard } from '@/components/onboarding/OnboardingWizard'
import { apiFetch } from '@/lib/api'

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))
vi.mock('@/components/anamnese/AnamneseView', () => ({
  AnamneseView: () => <div data-testid="anamnese" />,
}))
vi.mock('@/components/importar/GarminCard', () => ({
  GarminCard: () => <div data-testid="garmin-card" />,
}))

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

beforeEach(() => vi.clearAllMocks())

describe('OnboardingWizard', () => {
  it('passo 1 não avança sem perfil salvo', async () => {
    ;(apiFetch as Mock).mockResolvedValue(jsonRes(null, 200))
    render(<OnboardingWizard />)
    expect(screen.getByTestId('anamnese')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Continuar/ }))
    expect(await screen.findByText('Salve sua anamnese antes de continuar.')).toBeInTheDocument()
    expect(screen.queryByTestId('garmin-card')).not.toBeInTheDocument()
  })

  it('passo 1 avança quando o perfil existe; passo 2 é pulável; concluir chama o endpoint', async () => {
    ;(apiFetch as Mock).mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === 'athletes/me/profile') return jsonRes({ weekly_hours: 8 })
      if (path === 'auth/me/complete-onboarding' && init?.method === 'POST') return jsonRes(null, 204)
      throw new Error(`unexpected ${path}`)
    })
    const origLocation = window.location
    Object.defineProperty(window, 'location', {
      value: { ...origLocation, href: '' }, writable: true,
    })
    render(<OnboardingWizard />)
    fireEvent.click(screen.getByRole('button', { name: /Continuar/ }))
    expect(await screen.findByTestId('garmin-card')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Pular por enquanto/ }))
    expect(screen.getByText(/Tudo pronto/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Começar a treinar/ }))
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('auth/me/complete-onboarding', expect.objectContaining({ method: 'POST' })))
    Object.defineProperty(window, 'location', { value: origLocation, writable: true })
  })
})
