import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { formReading } from '@/lib/formState'
import { feedbackLine, hasStructured, riskBadge, workoutDescription, type RecSignals } from '@/lib/recs'
import type { Recommendation } from '@/lib/types'

const r = Math.round

export function RiskHeader({ rec }: { rec: Recommendation }) {
  const badge = riskBadge(rec.risk_level)
  return (
    <Card>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <Badge variant={badge.variant}>{badge.emoji} {badge.label}</Badge>
        {rec.confidence != null && (
          <span className="text-xs text-slate-500 dark:text-slate-400">Confiança: {Math.round(rec.confidence * 100)}%</span>
        )}
      </div>
      <p className="text-sm text-slate-700 dark:text-slate-200">{rec.summary}</p>
    </Card>
  )
}

export function SignalsPanel({ signals }: { signals: RecSignals }) {
  const form = signals.form ?? {}
  const tsb = form.tsb
  const fb = feedbackLine(signals.feedback)
  return (
    <Card title="🔍 Baseado em">
      <div className="grid grid-cols-3 gap-2 text-center">
        {([['Fitness (CTL)', form.ctl], ['Fadiga (ATL)', form.atl], ['Forma (TSB)', form.tsb]] as const).map(([k, v]) => (
          <div key={k}>
            <div className="text-[10px] uppercase tracking-wide text-slate-400">{k}</div>
            <div className="text-lg font-bold text-slate-700 dark:text-slate-100">{v != null ? r(v) : '—'}</div>
          </div>
        ))}
      </div>
      {tsb != null && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">Estado: {formReading(tsb)}</p>
      )}
      <div className="mt-3 grid grid-cols-1 gap-1 text-sm text-slate-600 dark:text-slate-300 sm:grid-cols-2">
        <div><span className="text-slate-400">Bloco atual:</span> <strong>{signals.block || '—'}</strong></div>
        <div><span className="text-slate-400">FTP usado:</span> <strong>{signals.ftp_watts ? `${r(signals.ftp_watts)} W` : '—'}</strong></div>
      </div>
      {signals.methodology && signals.methodology !== 'n/d' && (
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300"><span className="text-slate-400">Metodologia (perfil reverso real):</span> {signals.methodology}</p>
      )}
      {fb && <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{fb}</p>}
    </Card>
  )
}

function Field({ label, value }: { label: string; value: string | null }) {
  if (!value) return null
  return (
    <div className="text-sm">
      <span className="font-semibold text-slate-700 dark:text-slate-200">{label}:</span>{' '}
      <span className="text-slate-600 dark:text-slate-300">{value}</span>
    </div>
  )
}

export function RationalePanel({ rec }: { rec: Recommendation }) {
  return (
    <Card>
      <details>
        <summary className="cursor-pointer text-sm font-semibold text-slate-700 dark:text-slate-200">
          Justificativa, evidências e ajustes
        </summary>
        <div className="mt-3 space-y-2">
          <Field label="Objetivo fisiológico" value={rec.physiological_objective} />
          <Field label="Relação com o bloco" value={rec.block_relation} />
          <Field label="Racional" value={rec.rationale} />
          <Field label="Se mais cansado" value={rec.adjust_if_tired} />
          <Field label="Se menos tempo" value={rec.adjust_if_less_time} />
          {rec.evidence.length > 0 && (
            <div className="text-sm">
              <div className="font-semibold text-slate-700 dark:text-slate-200">Evidências (histórico real):</div>
              <ul className="mt-1 list-disc pl-5 text-slate-600 dark:text-slate-300">
                {rec.evidence.map((e, i) => <li key={i}>{e.description}</li>)}
              </ul>
            </div>
          )}
        </div>
      </details>
    </Card>
  )
}

export function StructuredWorkout({ rec }: { rec: Recommendation }) {
  const desc = workoutDescription(rec.payload)
  const structured = hasStructured(rec.payload)
  if (!desc && !structured) return null
  return (
    <Card title="🏋️ Treino estruturado">
      {desc && (
        <pre className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-700 dark:bg-slate-800/60 dark:text-slate-200">{desc}</pre>
      )}
      {structured && (
        <div className="mt-3 flex flex-wrap gap-2">
          {[['zwo', 'TrainingPeaks'], ['fit', 'dispositivo']].map(([ext, hint]) => (
            <a
              key={ext}
              href={`/api/proxy/recommendations/${rec.id}/export.${ext}`}
              download={`treino_${rec.id.slice(0, 8)}.${ext}`}
              className="rounded-lg border border-slate-300 px-3 py-1 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              ⬇️ .{ext} ({hint})
            </a>
          ))}
        </div>
      )}
    </Card>
  )
}
