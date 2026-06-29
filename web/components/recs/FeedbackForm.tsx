"use client";
import { useState } from 'react'
import { apiFetch } from '@/lib/api'
import { Card } from '@/components/ui/Card'

export function FeedbackForm({ recId }: { recId: string }) {
  const [rating, setRating] = useState(4)
  const [madeSense, setMadeSense] = useState(true)
  const [comment, setComment] = useState('')
  const [status, setStatus] = useState<'idle' | 'sending' | 'ok' | 'error'>('idle')

  async function submit() {
    setStatus('sending')
    try {
      const res = await apiFetch(`feedback/${recId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating, made_sense: madeSense, comment: comment || null }),
      })
      setStatus(res.ok ? 'ok' : 'error')
    } catch {
      setStatus('error')
    }
  }

  return (
    <Card title="Seu feedback após executar">
      <div className="space-y-3">
        <label className="block text-sm">
          <span className="text-slate-600 dark:text-slate-300">Nota: <strong>{rating}</strong>/5</span>
          <input type="range" min={1} max={5} value={rating} onChange={(e) => setRating(Number(e.target.value))} className="mt-1 w-full" />
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          <input type="checkbox" checked={madeSense} onChange={(e) => setMadeSense(e.target.checked)} />
          Fez sentido para mim
        </label>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Comentário (opcional)"
          className="w-full rounded-lg border border-slate-300 p-2 text-sm dark:border-slate-700 dark:bg-slate-800"
          rows={3}
        />
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={submit}
            disabled={status === 'sending'}
            className="rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
          >
            Enviar feedback
          </button>
          {status === 'ok' && <span className="text-sm text-emerald-600">Registrado. Obrigado!</span>}
          {status === 'error' && <span className="text-sm text-red-600">Falha ao enviar. Tente de novo.</span>}
        </div>
      </div>
    </Card>
  )
}
