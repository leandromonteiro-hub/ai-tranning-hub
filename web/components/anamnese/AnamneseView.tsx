"use client";
import { useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useProfile } from '@/lib/hooks'
import { fromProfile, toProfilePayload, type AnamneseForm } from '@/lib/anamnese'
import { Card } from '@/components/ui/Card'

const inputCls =
  'mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm dark:border-slate-700 dark:bg-slate-800'

function Text({ label, value, onChange, type = 'text' }: {
  label: string; value: string; onChange: (v: string) => void; type?: string
}) {
  return (
    <label className="text-sm">
      <span className="text-slate-600 dark:text-slate-300">{label}</span>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} className={inputCls} />
    </label>
  )
}

function Area({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="text-sm sm:col-span-2">
      <span className="text-slate-600 dark:text-slate-300">{label}</span>
      <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={2} className={inputCls} />
    </label>
  )
}

function AnamneseFormCard({ initial, onSaved }: { initial: AnamneseForm; onSaved: () => void }) {
  const [form, setForm] = useState<AnamneseForm>(initial)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<'idle' | 'ok' | 'error'>('idle')

  function upd<K extends keyof AnamneseForm>(key: K, value: AnamneseForm[K]) {
    setForm((f) => ({ ...f, [key]: value }))
    setStatus('idle')
  }

  async function save() {
    setSaving(true)
    setStatus('idle')
    try {
      const res = await apiFetch('athletes/me/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(toProfilePayload(form)),
      })
      if (!res.ok) { setStatus('error'); return }
      setStatus('ok')
      onSaved()
    } catch {
      setStatus('error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card title="Preencha seu perfil — obrigatório para gerar recomendações personalizadas">
      <div className="space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Text label="Data de nascimento" type="date" value={form.birth_date} onChange={(v) => upd('birth_date', v)} />
          <label className="text-sm">
            <span className="text-slate-600 dark:text-slate-300">Sexo</span>
            <select value={form.sex} onChange={(e) => upd('sex', e.target.value)} className={inputCls}>
              <option value="">—</option><option value="M">M</option><option value="F">F</option><option value="Outro">Outro</option>
            </select>
          </label>
          <Text label="Peso (kg)" type="number" value={form.weight_kg} onChange={(v) => upd('weight_kg', v)} />
          <Text label="Altura (cm)" type="number" value={form.height_cm} onChange={(v) => upd('height_cm', v)} />
          <Text label="FC máxima" type="number" value={form.max_hr} onChange={(v) => upd('max_hr', v)} />
          <Text label="FC repouso" type="number" value={form.resting_hr} onChange={(v) => upd('resting_hr', v)} />
          <Text label="Disciplina principal (ex.: XCO, Maratona)" value={form.primary_discipline} onChange={(v) => upd('primary_discipline', v)} />
          <Text label="Anos de treino" type="number" value={form.years_training} onChange={(v) => upd('years_training', v)} />
          <Text label="Disponibilidade (horas/semana)" type="number" value={form.weekly_hours} onChange={(v) => upd('weekly_hours', v)} />
          <Text label="Dias disponíveis/semana" type="number" value={form.weekly_days} onChange={(v) => upd('weekly_days', v)} />
          <Area label="Objetivos" value={form.goals} onChange={(v) => upd('goals', v)} />
          <Area label="Histórico de lesões/limitações" value={form.injury_history} onChange={(v) => upd('injury_history', v)} />
          <Area label="Condições médicas/medicações" value={form.medical_conditions} onChange={(v) => upd('medical_conditions', v)} />
        </div>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
            <input type="checkbox" checked={form.has_power_meter} onChange={(e) => upd('has_power_meter', e.target.checked)} />
            Tenho medidor de potência
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
            <input type="checkbox" checked={form.has_hr_monitor} onChange={(e) => upd('has_hr_monitor', e.target.checked)} />
            Tenho monitor de FC
          </label>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? 'Salvando…' : 'Salvar anamnese'}
          </button>
          {status === 'ok' && <span className="text-sm text-emerald-600">Anamnese salva.</span>}
          {status === 'error' && <span className="text-sm text-red-600">Não foi possível salvar. Tente de novo.</span>}
        </div>
      </div>
    </Card>
  )
}

export function AnamneseView() {
  const { data, isLoading, error, mutate } = useProfile()
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">🩺 Anamnese</h1>
      {isLoading ? (
        <p className="text-sm text-slate-500">Carregando…</p>
      ) : error && !data ? (
        // não renderiza o form em branco num erro de carga — evita sobrescrever o perfil
        <p className="text-sm text-red-600">Não foi possível carregar seu perfil. Recarregue a página.</p>
      ) : (
        <AnamneseFormCard key={data?.id ?? 'new'} initial={fromProfile(data)} onSaved={() => mutate()} />
      )}
    </div>
  )
}
