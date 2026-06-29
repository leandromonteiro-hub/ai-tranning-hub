"use client";
import { nameById } from '@/lib/admin'
import { useAdminAthletes, useAdminFeedback, useAdminUsage } from '@/lib/hooks'
import { Card } from '@/components/ui/Card'

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-2xl font-extrabold text-slate-800 dark:text-slate-100">{value}</div>
    </Card>
  )
}

function statusOf(e: unknown): number | undefined {
  return (e as { status?: number } | undefined)?.status
}

export function AdminView() {
  const usage = useAdminUsage()
  const athletes = useAdminAthletes()
  const feedback = useAdminFeedback()

  const forbidden = [usage.error, athletes.error, feedback.error].some((e) => statusOf(e) === 403)
  if (forbidden) {
    return (
      <div className="space-y-3">
        <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">📋 Painel do treinador</h1>
        <p className="text-sm text-slate-500">Acesso restrito ao treinador (perfil admin).</p>
      </div>
    )
  }

  const u = usage.data
  const names = nameById(athletes.data ?? [])

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">📋 Painel do treinador — validação</h1>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Metric label="Atletas" value={u?.athletes ?? '—'} />
        <Metric label="Treinos" value={u?.workouts ?? '—'} />
        <Metric label="Recomendações" value={u?.recommendations ?? '—'} />
        <Metric label="Feedbacks" value={u?.feedback_count ?? '—'} />
        <Metric label="Nota média" value={u ? u.avg_feedback_rating.toFixed(1) : '—'} />
      </div>

      <Card title="👥 Atletas">
        {(athletes.data?.length ?? 0) === 0 ? (
          <p className="text-sm text-slate-500">Nenhum atleta.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-slate-400"><th className="font-normal">Nome</th><th className="font-normal">Email</th><th className="font-normal">Ativo</th></tr></thead>
              <tbody>
                {athletes.data!.map((a) => (
                  <tr key={a.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1.5 text-slate-700 dark:text-slate-200">{a.full_name}</td>
                    <td className="py-1.5 text-slate-500">{a.email}</td>
                    <td className="py-1.5">{a.is_active ? '✅' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="💬 Feedbacks">
        {(feedback.data?.length ?? 0) === 0 ? (
          <p className="text-sm text-slate-500">Nenhum feedback ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-slate-400"><th className="font-normal">Atleta</th><th className="font-normal">Nota</th><th className="font-normal">Fez sentido</th><th className="font-normal">Comentário</th><th className="font-normal">Data</th></tr></thead>
              <tbody>
                {feedback.data!.map((f) => (
                  <tr key={f.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1.5 text-slate-700 dark:text-slate-200">{names[f.athlete_id] ?? f.athlete_id.slice(0, 8)}</td>
                    <td className="py-1.5 text-slate-500">{f.rating}</td>
                    <td className="py-1.5">{f.made_sense ? '✅' : '—'}</td>
                    <td className="py-1.5 text-slate-500">{f.comment || ''}</td>
                    <td className="py-1.5 text-slate-500">{(f.created_at || '').slice(0, 10)}</td>
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
