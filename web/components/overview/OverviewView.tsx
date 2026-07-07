"use client";
import Link from 'next/link'
import { Brain } from 'lucide-react'
import { useIntelligence, useCalendar, useRecommendations } from '@/lib/hooks'
import { addDaysIso, currentWeekSummary, mostRecentRec, nextPlannedWorkout } from '@/lib/overview'
import { todayIso } from '@/lib/dateUtils'
import { mondayOf } from '@/lib/weekRange'
import { formReading, formTone, TONE_TEXT } from '@/lib/formState'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'

const r = Math.round
const SIGN = (n: number) => (n > 0 ? `+${n}` : String(n))

function hhmm(secs: number | null | undefined): string {
  if (secs == null) return '—'
  let h = Math.floor(secs / 3600)
  let m = Math.round((secs % 3600) / 60)
  if (m === 60) { h += 1; m = 0 }
  return h > 0 ? `${h}h${String(m).padStart(2, '0')}` : `${m}min`
}

function FormaCard() {
  const { data: intel, isLoading } = useIntelligence()
  const form = intel?.form ?? null
  return (
    <Card title="Forma (TSB)">
      {isLoading ? (
        <div className="h-16 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
      ) : form ? (
        <Link href="/forma-carga" className="block">
          <div className={`text-4xl font-extrabold ${TONE_TEXT[formTone(r(form.tsb))]}`}>{SIGN(r(form.tsb))}</div>
          <div className={`mt-1 text-sm font-semibold ${TONE_TEXT[formTone(r(form.tsb))]}`}>{formReading(r(form.tsb))}</div>
          <div className="mt-2 text-xs text-slate-500">Fitness {r(form.ctl)} · Fadiga {r(form.atl)}</div>
        </Link>
      ) : (
        <div className="text-sm text-slate-500">
          Sem dados de forma ainda.{' '}
          <Link href="/importar" className="font-medium text-blue-600 underline">Importar treinos</Link>
        </div>
      )}
    </Card>
  )
}

function ProximoTreinoCard() {
  const today = todayIso()
  const { data: cal, isLoading } = useCalendar(mondayOf(today), addDaysIso(today, 14))
  const next = nextPlannedWorkout(cal, today)
  return (
    <Card title="Próximo treino">
      {isLoading ? (
        <div className="h-16 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
      ) : next ? (
        <Link href="/plano" className="block">
          <div className="text-lg font-bold text-slate-800 dark:text-slate-100">{next.name}</div>
          <div className="mt-1 text-xs text-slate-500">
            {next.planned_date} · {next.workout_type} · {hhmm(next.planned_duration_s)}
            {next.planned_tss != null ? ` · TSS ${r(next.planned_tss)}` : ''}
          </div>
        </Link>
      ) : (
        <div className="text-sm text-slate-500">
          Nenhum treino planejado.{' '}
          <Link href="/recomendacoes" className="font-medium text-blue-600 underline">Gerar</Link>
        </div>
      )}
    </Card>
  )
}

function SemanaCard() {
  const today = todayIso()
  const { data: cal, isLoading: loadingCal } = useCalendar(mondayOf(today), addDaysIso(today, 14))
  const { data: recs, isLoading: loadingRecs } = useRecommendations()
  const week = currentWeekSummary(cal, today)
  const rec = mostRecentRec(recs)
  return (
    <Card title="Semana + recomendação">
      {loadingCal ? (
        <div className="h-16 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
      ) : (
        <div className="flex gap-6 text-sm">
          <div><div className="text-2xl font-bold text-slate-800 dark:text-slate-100">{week ? r(week.total_tss) : 0}</div><div className="text-xs text-slate-500">TSS</div></div>
          <div><div className="text-2xl font-bold text-slate-800 dark:text-slate-100">{hhmm(week?.total_duration_s ?? 0)}</div><div className="text-xs text-slate-500">tempo</div></div>
          <div><div className="text-2xl font-bold text-slate-800 dark:text-slate-100">{week ? r(week.total_distance_m / 1000) : 0}</div><div className="text-xs text-slate-500">km</div></div>
        </div>
      )}
      <div className="mt-3 border-t border-slate-100 pt-3 dark:border-slate-800">
        {loadingRecs ? (
          <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100 dark:bg-slate-800" />
        ) : rec ? (
          <Link href="/recomendacoes" className="block text-sm text-slate-600 hover:underline dark:text-slate-300">
            {rec.summary.length > 120 ? rec.summary.slice(0, 120) + '…' : rec.summary}
          </Link>
        ) : (
          <div className="text-sm text-slate-500">
            Nenhuma recomendação ainda.{' '}
            <Link href="/recomendacoes" className="font-medium text-blue-600 underline">Gerar</Link>
          </div>
        )}
      </div>
    </Card>
  )
}

export function OverviewView() {
  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100 sm:text-2xl">Visão geral</h1>
          <p className="text-sm text-slate-500">Seu painel de treino.</p>
        </div>
        <Link href="/recomendacoes">
          <Button><Brain className="h-4 w-4" /> Gerar recomendação</Button>
        </Link>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <FormaCard />
        <ProximoTreinoCard />
        <SemanaCard />
      </div>
    </div>
  )
}
