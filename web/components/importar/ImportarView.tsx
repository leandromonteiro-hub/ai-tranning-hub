"use client";
import { useEffect, useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { pollDecision } from '@/lib/jobPoll'
import type { JobStatus, UploadResponse } from '@/lib/types'
import { Card } from '@/components/ui/Card'

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))
type ProfileState = 'idle' | 'polling' | 'done' | 'failed' | 'giveup'

const PROFILE_MSG: Record<Exclude<ProfileState, 'idle'>, string> = {
  polling: '🔄 Atualizando seu perfil…',
  done: '✅ Perfil atualizado.',
  failed: 'O perfil será atualizado em instantes.',
  giveup: 'O perfil está sendo atualizado em segundo plano.',
}

export function ImportarView() {
  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<UploadResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [profile, setProfile] = useState<ProfileState>('idle')
  const cancelled = useRef(false)

  useEffect(() => () => { cancelled.current = true }, [])

  async function pollProfile(taskId: string) {
    setProfile('polling')
    const max = 30
    for (let attempt = 1; attempt <= max; attempt++) {
      if (cancelled.current) return
      let state = 'PENDING'
      try {
        const r = await apiFetch(`jobs/${taskId}`)
        if (r.ok) state = ((await r.json()) as JobStatus).state
      } catch { /* trata como PENDING e segue */ }
      const d = pollDecision(state, attempt, max)
      if (d !== 'continue') { if (!cancelled.current) setProfile(d); return }
      await sleep(1500)
    }
  }

  async function upload() {
    if (files.length === 0) return
    setUploading(true); setError(null); setResult(null); setProfile('idle')
    try {
      const fd = new FormData()
      for (const f of files) fd.append('files', f)
      const res = await apiFetch('imports/upload', { method: 'POST', body: fd })
      if (!res.ok) { setError('Falha no upload. Verifique os arquivos e tente de novo.'); return }
      const body = (await res.json()) as UploadResponse
      setResult(body)
      if (body.profile_task_id) void pollProfile(body.profile_task_id)
    } catch {
      setError('Falha no upload. Tente de novo.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">📥 Importar treinos</h1>

      <Card title="Enviar arquivos (CSV TrainingPeaks, FIT, TCX, GPX)">
        <div className="space-y-3">
          <input
            type="file"
            multiple
            accept=".csv,.fit,.tcx,.gpx"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-slate-800 dark:text-slate-300 dark:file:bg-slate-100 dark:file:text-slate-900"
          />
          {files.length > 0 && <p className="text-xs text-slate-500">{files.length} arquivo(s) selecionado(s)</p>}
          <button
            type="button"
            onClick={upload}
            disabled={uploading || files.length === 0}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Upload className="h-4 w-4" />
            {uploading ? 'Enviando…' : 'Enviar'}
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
      </Card>

      {result && (
        <Card title="Importação concluída">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-400">
                  <th className="font-normal">Arquivo</th><th className="font-normal">Formato</th>
                  <th className="font-normal">Status</th><th className="font-normal">Linhas</th>
                </tr>
              </thead>
              <tbody>
                {result.files.map((f) => (
                  <tr key={f.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1 text-slate-700 dark:text-slate-200">{f.filename}</td>
                    <td className="py-1 text-slate-500">{f.file_format}</td>
                    <td className="py-1 text-slate-500">{f.error_message ? `erro: ${f.error_message}` : f.status}</td>
                    <td className="py-1 text-slate-500">{f.rows_imported}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {profile !== 'idle' && (
            <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{PROFILE_MSG[profile]}</p>
          )}
        </Card>
      )}
    </div>
  )
}
