"use client";
import { useState } from 'react'
import { apiFetch } from '@/lib/api'
import { recoveryBody, subjectiveBody, type CheckinForm } from '@/lib/checkin'
import { Card } from '@/components/ui/Card'

const inputCls =
  'mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm dark:border-slate-700 dark:bg-slate-800'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function NumField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="text-sm">
      <span className="text-slate-600 dark:text-slate-300">{label}</span>
      <input type="number" value={value} onChange={(e) => onChange(e.target.value)} className={inputCls} />
    </label>
  )
}

function Slider({ label, value, onChange, hint }: { label: string; value: number; onChange: (v: number) => void; hint: string }) {
  return (
    <label className="block text-sm">
      <span className="text-slate-600 dark:text-slate-300">{label}: <strong>{value}</strong> <span className="text-xs text-slate-400">{hint}</span></span>
      <input type="range" min={1} max={5} value={value} onChange={(e) => onChange(Number(e.target.value))} className="mt-1 w-full" />
    </label>
  )
}

export function CheckinView() {
  const [form, setForm] = useState<CheckinForm>({
    sleep_hours: '7', resting_hr: '55', hrv_ms: '', fatigue: 3, soreness: 2,
    mood: 4, motivation: 4, injury_flag: false, comment: '',
  })
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<'idle' | 'ok' | 'error'>('idle')

  function upd<K extends keyof CheckinForm>(key: K, value: CheckinForm[K]) {
    setForm((f) => ({ ...f, [key]: value }))
    setStatus('idle')
  }

  async function submit() {
    setSaving(true)
    setStatus('idle')
    try {
      const today = todayIso()
      const post = (path: string, body: unknown) =>
        apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      const [rec, sub] = await Promise.all([
        post('metrics/recovery', recoveryBody(form, today)),
        post('metrics/subjective', subjectiveBody(form, today)),
      ])
      setStatus(rec.ok && sub.ok ? 'ok' : 'error')
    } catch {
      setStatus('error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">📝 Check-in diário</h1>
      <Card title="Como você está hoje? Isso ajusta a recomendação ao seu estado atual.">
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <NumField label="Horas de sono" value={form.sleep_hours} onChange={(v) => upd('sleep_hours', v)} />
            <NumField label="FC repouso hoje" value={form.resting_hr} onChange={(v) => upd('resting_hr', v)} />
            <NumField label="HRV (ms, opcional)" value={form.hrv_ms} onChange={(v) => upd('hrv_ms', v)} />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Slider label="Fadiga" hint="(1 ótimo – 5 exausto)" value={form.fatigue} onChange={(v) => upd('fatigue', v)} />
            <Slider label="Dor muscular" hint="(1 – 5)" value={form.soreness} onChange={(v) => upd('soreness', v)} />
            <Slider label="Humor" hint="(1 – 5)" value={form.mood} onChange={(v) => upd('mood', v)} />
            <Slider label="Motivação" hint="(1 – 5)" value={form.motivation} onChange={(v) => upd('motivation', v)} />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
            <input type="checkbox" checked={form.injury_flag} onChange={(e) => upd('injury_flag', e.target.checked)} />
            Dor/lesão hoje
          </label>
          <label className="block text-sm">
            <span className="text-slate-600 dark:text-slate-300">Comentário</span>
            <textarea value={form.comment} onChange={(e) => upd('comment', e.target.value)} rows={2} className={inputCls} />
          </label>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={submit}
              disabled={saving}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Registrando…' : 'Registrar check-in'}
            </button>
            {status === 'ok' && <span className="text-sm text-emerald-600">Check-in registrado. A próxima recomendação considerará seu estado de hoje.</span>}
            {status === 'error' && <span className="text-sm text-red-600">Não foi possível registrar. Tente de novo.</span>}
          </div>
        </div>
      </Card>
    </div>
  )
}
