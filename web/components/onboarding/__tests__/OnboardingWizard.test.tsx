import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { OnboardingWizard } from '@/components/onboarding/OnboardingWizard'
import { apiFetch } from '@/lib/api'

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))
vi.mock('@/components/anamnese/AnamneseView', () => ({
  AnamneseView: () => <div data-testid="anamnese" />,
}))
vi.mock('@/components/importar/FileUploader', () => ({
  FileUploader: () => <div data-testid="file-uploader" />,
}))
vi.mock('@/components/importar/GarminCard', () => ({
  GarminCard: () => <div data-testid="garmin-card" />,
}))

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

beforeEach(() => vi.clearAllMocks())

describe('OnboardingWizard', () => {
  it('passo 1 (anamnese) não avança com perfil incompleto', async () => {
    ;(apiFetch as Mock).mockResolvedValue(jsonRes({ birth_date: '1990-01-01' })) // faltam campos
    render(<OnboardingWizard />)
    fireEvent.click(screen.getByRole('button', { name: /Continuar/ }))
    expect(await screen.findByText(/Preencha os campos obrigatórios/)).toBeInTheDocument()
    expect(screen.queryByTestId('file-uploader')).not.toBeInTheDocument()
  })

  it('anamnese completa → passo Importar histórico (FileUploader), pulável → Garmin', async () => {
    const complete = {
      birth_date: '1990-01-01', sex: 'M', weight_kg: 70, height_cm: 175, max_hr: 185,
      primary_discipline: 'XCM', years_training: 5, goals: 'ultra', weekly_hours: 10,
    }
    ;(apiFetch as Mock).mockResolvedValue(jsonRes(complete))
    render(<OnboardingWizard />)
    fireEvent.click(screen.getByRole('button', { name: /Continuar/ }))
    expect(await screen.findByTestId('file-uploader')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Pular por enquanto/ }))
    expect(screen.getByTestId('garmin-card')).toBeInTheDocument()
  })

  it('fluxo completo: anamnese → histórico → garmin → concluir', async () => {
    ;(apiFetch as Mock).mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === 'athletes/me/profile') return jsonRes({
        id: 'p', athlete_id: 'a', birth_date: '1990-01-01', sex: 'M', weight_kg: 70,
        height_cm: 175, max_hr: 185, resting_hr: 50, primary_discipline: 'XCM',
        years_training: 5, notes: null, goals: 'ultra', weekly_hours: 10, weekly_days: 5,
        injury_history: null, medical_conditions: null, has_power_meter: true, has_hr_monitor: true,
      })
      if (path === 'auth/me/complete-onboarding' && init?.method === 'POST') return jsonRes(null, 204)
      throw new Error(`unexpected ${path}`)
    })
    const origLocation = window.location
    Object.defineProperty(window, 'location', {
      value: { ...origLocation, href: '' }, writable: true,
    })
    render(<OnboardingWizard />)
    fireEvent.click(screen.getByRole('button', { name: /Continuar/ }))
    expect(await screen.findByTestId('file-uploader')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Pular por enquanto/ }))
    expect(screen.getByTestId('garmin-card')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Pular por enquanto/ }))
    expect(screen.getByText(/Tudo pronto/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Começar a treinar/ }))
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('auth/me/complete-onboarding', expect.objectContaining({ method: 'POST' })))
    await waitFor(() => expect(window.location.href).toBe('/'))
    Object.defineProperty(window, 'location', { value: origLocation, writable: true })
  })
})
