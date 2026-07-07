"use client";
import { useState } from 'react'
import { apiFetch } from '@/lib/api'
import { AnamneseView } from '@/components/anamnese/AnamneseView'
import { GarminCard } from '@/components/importar/GarminCard'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

const STEPS = ['Anamnese', 'Garmin', 'Concluir'] as const

export function OnboardingWizard() {
  const [step, setStep] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function advanceFromAnamnese() {
    setBusy(true); setError('')
    try {
      const res = await apiFetch('athletes/me/profile')
      const profile = res.ok ? await res.json() : null
      if (!profile) {
        setError('Salve sua anamnese antes de continuar.')
        return
      }
      setStep(1)
    } catch {
      setError('Não foi possível verificar seu perfil. Tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  async function complete() {
    setBusy(true); setError('')
    try {
      const res = await apiFetch('auth/me/complete-onboarding', { method: 'POST' })
      if (!res.ok) { setError('Não foi possível concluir. Tente novamente.'); return }
      // Reload completo: o gate do layout (server) precisa reavaliar o estado.
      window.location.href = '/'
    } catch {
      setError('Não foi possível concluir. Tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5 p-4 sm:p-8">
      <div className="flex items-center gap-2">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <span
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                i <= step ? 'bg-blue-600 text-white' : 'bg-slate-200 text-slate-500 dark:bg-slate-700'
              }`}
            >
              {i + 1}
            </span>
            <span className="text-sm text-slate-600 dark:text-slate-300">{label}</span>
            {i < STEPS.length - 1 && <span className="w-6 h-px bg-slate-300 dark:bg-slate-600" />}
          </div>
        ))}
      </div>

      {step === 0 && (
        <div className="space-y-4">
          <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">
            Bem-vindo! Primeiro, sua anamnese
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Sem ela o treinador IA não gera recomendações personalizadas.
          </p>
          <AnamneseView />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="button" onClick={advanceFromAnamnese} disabled={busy}>
            {busy ? 'Verificando…' : 'Continuar'}
          </Button>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-4">
          <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">
            Conecte seu Garmin (opcional)
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Importa seus treinos e recuperação automaticamente. Dá para fazer depois na página Importar.
          </p>
          <GarminCard />
          <div className="flex gap-2">
            <Button type="button" onClick={() => setStep(2)}>Continuar</Button>
            <Button type="button" variant="secondary" onClick={() => setStep(2)}>
              Pular por enquanto
            </Button>
          </div>
        </div>
      )}

      {step === 2 && (
        <Card title="Tudo pronto 🎉">
          <div className="space-y-4">
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Seu perfil está criado. Importe seus treinos históricos na página Importar
              para o treinador IA conhecer você mais rápido.
            </p>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button type="button" onClick={complete} disabled={busy}>
              {busy ? 'Concluindo…' : 'Começar a treinar'}
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}
