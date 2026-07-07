"use client";
import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { useRecommendations } from '@/lib/hooks'
import { signalsOf } from '@/lib/recs'
import type { Recommendation } from '@/lib/types'
import { Card } from '@/components/ui/Card'
import { FeedbackForm } from '@/components/recs/FeedbackForm'
import { RationalePanel, RiskHeader, SignalsPanel, ComparativeWorkouts } from '@/components/recs/RecsSections'

function mostRecent(recs: Recommendation[] | undefined): Recommendation | null {
  if (!recs || recs.length === 0) return null
  return [...recs].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
}

export function RecomendacoesView() {
  const { data: recs, mutate } = useRecommendations()
  const [question, setQuestion] = useState('Qual treino devo fazer hoje?')
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [current, setCurrent] = useState<Recommendation | null>(null)

  const rec = current ?? mostRecent(recs)

  async function generate() {
    setGenerating(true)
    setError(null)
    try {
      const res = await apiFetch('recommendations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      if (!res.ok) {
        setError(res.status === 422 ? 'Complete sua anamnese para gerar recomendações.' : 'Não foi possível gerar agora. Tente de novo.')
        return
      }
      setCurrent((await res.json()) as Recommendation)
      await mutate()
    } catch {
      setError('Não foi possível gerar agora. Tente de novo.')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">🧠 Recomendação de treino</h1>

      <Card>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex-1 text-sm">
            <span className="text-slate-600 dark:text-slate-300">Pergunta (opcional)</span>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm dark:border-slate-700 dark:bg-slate-800"
            />
          </label>
          <button
            type="button"
            onClick={generate}
            disabled={generating}
            className="flex items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Sparkles className="h-4 w-4" />
            {generating ? 'Gerando…' : 'Gerar recomendação'}
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        {generating && <p className="mt-2 text-xs text-slate-500">A IA está montando sua recomendação — pode levar alguns segundos.</p>}
      </Card>

      {rec && (
        <>
          <RiskHeader rec={rec} />
          <SignalsPanel signals={signalsOf(rec.payload)} />
          <RationalePanel rec={rec} />
          <ComparativeWorkouts rec={rec} onChosen={() => void mutate()} />
          <FeedbackForm key={rec.id} recId={rec.id} />
        </>
      )}
    </div>
  )
}
