"use client";
import { useState } from 'react'
import { Flag, Plus } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { useRaces } from '@/lib/hooks'
import { priorityVariant, sortRacesByDate } from '@/lib/races'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'

const inputCls =
  'mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm dark:border-slate-700 dark:bg-slate-800'

export function ProvasView() {
  const { data: races, mutate } = useRaces()
  const [name, setName] = useState('')
  const [raceDate, setRaceDate] = useState('')
  const [discipline, setDiscipline] = useState('')
  const [priority, setPriority] = useState('A')
  const [showDetails, setShowDetails] = useState(false)
  const [location, setLocation] = useState('')
  const [distanceKm, setDistanceKm] = useState('')
  const [elevation, setElevation] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  function reset() {
    setName(''); setRaceDate(''); setDiscipline(''); setPriority('A')
    setLocation(''); setDistanceKm(''); setElevation(''); setNotes(''); setShowDetails(false)
  }

  async function submit() {
    if (!name.trim()) { setError('Informe o nome da prova.'); return }
    if (!raceDate) { setError('Informe a data da prova.'); return }
    setSaving(true); setError(null)
    try {
      const body = {
        name: name.trim(),
        race_date: raceDate,
        discipline: discipline || null,
        priority,
        location: location || null,
        distance_km: distanceKm ? Number(distanceKm) : null,
        elevation_gain_m: elevation ? Number(elevation) : null,
        notes: notes || null,
      }
      const res = await apiFetch('races', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) { setError('Não foi possível cadastrar a prova.'); return }
      reset()
      await mutate()
    } catch {
      setError('Não foi possível cadastrar a prova.')
    } finally {
      setSaving(false)
    }
  }

  const list = sortRacesByDate(races ?? [])

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">🏁 Provas-alvo</h1>

      <Card title="Cadastrar prova">
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="text-sm">
              <span className="text-slate-600 dark:text-slate-300">Nome da prova</span>
              <input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
            </label>
            <label className="text-sm">
              <span className="text-slate-600 dark:text-slate-300">Data</span>
              <input type="date" value={raceDate} onChange={(e) => setRaceDate(e.target.value)} className={inputCls} />
            </label>
            <label className="text-sm">
              <span className="text-slate-600 dark:text-slate-300">Disciplina (ex.: XCO, Maratona)</span>
              <input value={discipline} onChange={(e) => setDiscipline(e.target.value)} className={inputCls} />
            </label>
            <label className="text-sm">
              <span className="text-slate-600 dark:text-slate-300">Prioridade</span>
              <select value={priority} onChange={(e) => setPriority(e.target.value)} className={inputCls}>
                <option value="A">A</option><option value="B">B</option><option value="C">C</option>
              </select>
            </label>
          </div>

          <button type="button" onClick={() => setShowDetails((v) => !v)} className="text-xs font-medium text-blue-600 dark:text-blue-400">
            {showDetails ? '− Menos detalhes' : '+ Mais detalhes (opcional)'}
          </button>
          {showDetails && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="text-sm">
                <span className="text-slate-600 dark:text-slate-300">Local</span>
                <input value={location} onChange={(e) => setLocation(e.target.value)} className={inputCls} />
              </label>
              <label className="text-sm">
                <span className="text-slate-600 dark:text-slate-300">Distância (km)</span>
                <input type="number" min={0} value={distanceKm} onChange={(e) => setDistanceKm(e.target.value)} className={inputCls} />
              </label>
              <label className="text-sm">
                <span className="text-slate-600 dark:text-slate-300">Ganho de elevação (m)</span>
                <input type="number" min={0} value={elevation} onChange={(e) => setElevation(e.target.value)} className={inputCls} />
              </label>
              <label className="text-sm sm:col-span-2">
                <span className="text-slate-600 dark:text-slate-300">Notas</span>
                <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className={inputCls} />
              </label>
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={submit}
              disabled={saving}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <Plus className="h-4 w-4" />
              {saving ? 'Salvando…' : 'Cadastrar prova'}
            </button>
            {error && <span className="text-sm text-red-600">{error}</span>}
          </div>
        </div>
      </Card>

      <Card title="Suas provas">
        {list.length === 0 ? (
          <p className="text-sm text-slate-500">Nenhuma prova cadastrada ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-400">
                  <th className="font-normal">Data</th><th className="font-normal">Prova</th>
                  <th className="font-normal">Prioridade</th><th className="font-normal">Disciplina</th><th className="font-normal">Local</th>
                </tr>
              </thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1.5 text-slate-700 dark:text-slate-200">{r.race_date}</td>
                    <td className="py-1.5 text-slate-700 dark:text-slate-200">
                      <span className="flex items-center gap-1.5"><Flag className="h-3 w-3 text-slate-400" />{r.name}</span>
                    </td>
                    <td className="py-1.5"><Badge variant={priorityVariant(r.priority)}>{r.priority}</Badge></td>
                    <td className="py-1.5 text-slate-500">{r.discipline || '—'}</td>
                    <td className="py-1.5 text-slate-500">{r.location || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
