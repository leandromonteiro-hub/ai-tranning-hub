import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { formReading, formTone, richnessLabel, TONE_TEXT } from '@/lib/formState'
import type { Block, DataRichness, IntensitySplit } from '@/lib/formState'
import type { FormState, FtpPoint } from '@/lib/types'

const r = Math.round
const SIGN = (n: number) => (n > 0 ? `+${n}` : String(n))

// 1) Estado de forma
export function FormCards({ form }: { form: FormState }) {
  const ctl = r(form.ctl)
  const atl = r(form.atl)
  const tsb = r(form.tsb)
  const tone = TONE_TEXT[formTone(tsb)]
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Card title="Fitness (CTL)"><div className="text-3xl font-extrabold text-slate-800 dark:text-slate-100">{ctl}</div></Card>
      <Card title="Fadiga (ATL)"><div className="text-3xl font-extrabold text-slate-800 dark:text-slate-100">{atl}</div></Card>
      <Card title="Forma (TSB)">
        <div className={`text-3xl font-extrabold ${tone}`}>{SIGN(tsb)}</div>
        <div className={`mt-1 text-sm font-semibold ${tone}`}>{formReading(tsb)}</div>
      </Card>
    </div>
  )
}

// 3) FTP por período
export function FtpBars({ ftps }: { ftps: FtpPoint[] }) {
  if (ftps.length === 0) return null
  const max = Math.max(...ftps.map((f) => f.ftp_watts), 1)
  return (
    <div className="flex h-32 items-end gap-2">
      {ftps.map((f) => (
        <div key={f.valid_from} className="flex flex-1 flex-col items-center gap-1">
          <span className="text-xs font-bold text-slate-700 dark:text-slate-200">{r(f.ftp_watts)}</span>
          <div className="w-3/5 rounded-t bg-emerald-500" style={{ height: `${Math.max(4, (f.ftp_watts / max) * 96)}px` }} />
          <span className="text-[10px] font-medium text-slate-400">{f.valid_from.slice(0, 7)}</span>
        </div>
      ))}
    </div>
  )
}

// 4) Curva de potência (melhores marcas)
export function PowerCurveBars({ bests }: { bests: Record<string, number> }) {
  const items = Object.entries(bests)
  if (items.length === 0) return null
  const max = Math.max(...items.map(([, w]) => w), 1)
  return (
    <div className="flex h-32 items-end gap-2">
      {items.map(([label, watts]) => (
        <div key={label} className="flex flex-1 flex-col items-center gap-1">
          <span className="text-xs font-bold text-slate-700 dark:text-slate-200">{r(watts)}<span className="text-[9px] text-slate-400"> W</span></span>
          <div className="w-3/5 rounded-t bg-blue-600" style={{ height: `${Math.max(4, (watts / max) * 96)}px` }} />
          <span className="text-[10px] font-medium text-slate-400">{label}</span>
        </div>
      ))}
    </div>
  )
}

// 5) Distribuição de intensidade
const SPLIT = [
  { key: 'z1_pct', name: 'Fácil', color: '#3b82f6' },
  { key: 'z2_pct', name: 'Moderado', color: '#f5b400' },
  { key: 'z3_pct', name: 'Forte', color: '#ef4444' },
] as const

export function IntensitySplit({ split }: { split: IntensitySplit }) {
  const segs = SPLIT.map((s) => ({ ...s, pct: Math.round((Number(split[s.key] ?? 0)) * 100) })).filter((s) => s.pct > 0)
  if (segs.length === 0) return null
  return (
    <div>
      <div className="flex h-6 w-full overflow-hidden rounded-md">
        {segs.map((s) => <div key={s.key} style={{ width: `${s.pct}%`, background: s.color }} />)}
      </div>
      <div className="mt-2 flex flex-wrap gap-4">
        {segs.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
            {s.name} {s.pct}%
          </span>
        ))}
      </div>
    </div>
  )
}

// 6) Periodização real
const BLOCK_COLORS: Record<string, string> = {
  base: '#3b82f6', build: '#ff8a3d', peak: '#ef4444', taper: '#8b5cf6', recovery: '#10b981',
}

export function BlocksList({ blocks }: { blocks: Block[] }) {
  if (blocks.length === 0) return null
  const recent = blocks.slice(-6).reverse()
  return (
    <div className="space-y-1.5">
      {recent.map((b, i) => {
        const bt = (b.block_type ?? '').toLowerCase()
        return (
          <div key={i} className="flex items-baseline gap-2 text-xs">
            <span className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-extrabold uppercase tracking-wide text-white" style={{ background: BLOCK_COLORS[bt] ?? '#8a93a3' }}>
              {(b.block_type ?? '').toUpperCase()}
            </span>
            <span className="text-slate-500 dark:text-slate-400">{b.evidence ?? ''}</span>
          </div>
        )
      })}
    </div>
  )
}

// 7) Riqueza dos dados
export function DataRichnessCard({ dr }: { dr: DataRichness }) {
  if (dr.score == null) return null
  const label = dr.label ?? richnessLabel(dr.score)
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Badge variant="success">{label} · score {dr.score.toFixed(2)}</Badge>
      <span className="text-xs text-slate-500 dark:text-slate-400">
        {dr.n_workouts != null && `${dr.n_workouts} treinos`}
        {dr.years_covered != null && ` · ${dr.years_covered.toFixed(1)} anos`}
      </span>
    </div>
  )
}
