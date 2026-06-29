"use client";
import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { useIntelligence, useLoadSeries } from '@/lib/hooks'
import { powerCurve, type TwinSeed } from '@/lib/formState'
import { Card } from '@/components/ui/Card'
import { PmcChart } from '@/components/forma/PmcChart'
import {
  BlocksList, DataRichnessCard, FormCards, FtpBars, IntensitySplit, PowerCurveBars,
} from '@/components/forma/FormaSections'

function isoDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

export function FormaCargaView() {
  const { data: intel, isLoading, error, mutate: mutateIntel } = useIntelligence()
  const start = isoDaysAgo(180)
  const end = new Date().toISOString().slice(0, 10)
  const { data: load, mutate: mutateLoad } = useLoadSeries(start, end)
  const [recomputing, setRecomputing] = useState(false)

  async function recompute() {
    setRecomputing(true)
    try {
      await apiFetch('metrics/load/recompute', { method: 'POST' })
      await Promise.all([mutateLoad(), mutateIntel()])
    } finally {
      setRecomputing(false)
    }
  }

  if (isLoading) return <p className="text-sm text-slate-500">Carregando…</p>
  if (error || !intel) return <p className="text-sm text-red-600">Erro ao carregar a inteligência.</p>

  const twin = (intel.twin_seed ?? null) as TwinSeed | null
  const bests = powerCurve(twin)
  const split = twin?.intensity_split
  const blocks = twin?.block_summary ?? []
  const dr = twin?.data_richness

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">📈 Forma &amp; Carga</h1>

      {intel.form && <FormCards form={intel.form} />}

      <Card
        title="Tendência · Fitness (CTL) · Fadiga (ATL) · Forma (TSB)"
        action={
          <button
            type="button"
            onClick={recompute}
            disabled={recomputing}
            className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${recomputing ? 'animate-spin' : ''}`} />
            Recalcular
          </button>
        }
      >
        <PmcChart series={load ?? []} />
      </Card>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {intel.ftp_history.length > 0 && (
          <Card title={`⚡ FTP · atual ${Math.round(intel.ftp_history[intel.ftp_history.length - 1].ftp_watts)} W`}>
            <FtpBars ftps={intel.ftp_history} />
          </Card>
        )}
        {bests && (
          <Card title="🚴 Curva de potência (melhores marcas)">
            <PowerCurveBars bests={bests} />
          </Card>
        )}
      </div>

      {split && (
        <Card title={`🎯 Distribuição de intensidade · ${split.label ?? ''}`}>
          <IntensitySplit split={split} />
        </Card>
      )}

      {blocks.length > 0 && (
        <Card title={`🧱 Periodização real · ${blocks.length} blocos detectados`}>
          <BlocksList blocks={blocks} />
        </Card>
      )}

      {dr?.score != null && (
        <Card title="📊 Riqueza dos dados">
          <DataRichnessCard dr={dr} />
        </Card>
      )}
    </div>
  )
}
