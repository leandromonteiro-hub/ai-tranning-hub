"use client";
import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { WorkoutStreams } from '@/lib/types'
import type { Segment } from '@/lib/structure'
import { zoneColor } from '@/lib/zones'
import { streamToBars } from '@/components/workout/profileData'

const HR_COLOR = '#ef4444'

/** Legenda compacta: deixa explícito o que é potência (W) e o que é FC (bpm). */
function ChartLegend({ hasHr }: { hasHr: boolean }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
      <span className="flex items-center gap-1.5">
        <span className="inline-flex h-3 w-5 overflow-hidden rounded-sm" aria-hidden>
          {[1, 2, 3, 4, 5].map((z) => (
            <span key={z} className="h-full flex-1" style={{ background: zoneColor(z) }} />
          ))}
        </span>
        <strong className="font-semibold text-slate-600 dark:text-slate-300">Potência (W)</strong>
        <span>— barras coloridas por zona</span>
      </span>
      {hasHr && (
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-5 rounded" style={{ background: HR_COLOR }} aria-hidden />
          <strong className="font-semibold text-slate-600 dark:text-slate-300">FC (bpm)</strong>
          <span>— linha vermelha (eixo à direita)</span>
        </span>
      )}
    </div>
  )
}

function PlannedSvg({ segments }: { segments: Segment[] }) {
  const total = segments.reduce((a, s) => a + s.durationS, 0) || 1
  const maxW = Math.max(1, ...segments.map((s) => s.highW ?? 0))
  let x = 0
  return (
    <div>
      <svg width="100%" height={120} viewBox="0 0 100 120" preserveAspectRatio="none" role="img" aria-label="Perfil planejado">
        {segments.map((s, i) => {
          const w = (s.durationS / total) * 100
          const h = ((s.highW ?? maxW * 0.4) / maxW) * 120
          const rect = <rect key={i} x={x} y={120 - h} width={w} height={h} fill={zoneColor(s.zone)} />
          x += w
          return rect
        })}
      </svg>
      <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        <strong className="font-semibold text-slate-600 dark:text-slate-300">Potência planejada (W)</strong> — cores = zonas (sem FC no planejado)
      </div>
    </div>
  )
}

function StreamPlot({ streams, ftp }: { streams: WorkoutStreams; ftp: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const hasHr = streams.heart_rate.some((v) => v != null)

  useEffect(() => {
    if (!ref.current) return
    const bars = streamToBars(streams.power, ftp)
    const xs = bars.map((_, i) => i)
    const powerYs = bars.map((b) => b.value)
    const hrYs = streams.heart_rate

    const axes: uPlot.Axis[] = [
      { show: false },
      // eixo esquerdo: Potência (W)
      { scale: 'y', size: 42, label: 'Potência (W)', labelSize: 12 },
    ]
    const series: uPlot.Series[] = [
      {},
      {
        scale: 'y',
        stroke: '#1d4ed8',
        width: 1,
        // barras verticais coloridas por zona (potência)
        paths: (u, sidx, i0, i1) => {
          const ctx = (u as unknown as { ctx: CanvasRenderingContext2D }).ctx
          for (let i = i0; i <= i1; i++) {
            const v = u.data[sidx][i]
            if (v == null) continue
            const xv = u.valToPos(u.data[0][i] as number, 'x', true)
            const yv = u.valToPos(v as number, 'y', true)
            const y0 = u.valToPos(0, 'y', true)
            ctx.beginPath()
            ctx.strokeStyle = zoneColor(bars[i].zone)
            ctx.moveTo(xv, y0)
            ctx.lineTo(xv, yv)
            ctx.stroke()
          }
          return { stroke: new Path2D() }
        },
      },
    ]
    const data: uPlot.AlignedData = [xs, powerYs]

    if (hasHr) {
      // eixo direito: FC (bpm), escala própria (bpm ~100-190 não polui a de W)
      axes.push({ scale: 'hr', side: 1, size: 42, label: 'FC (bpm)', labelSize: 12, stroke: () => HR_COLOR })
      series.push({ scale: 'hr', stroke: HR_COLOR, width: 1.4, spanGaps: true })
      data.push(hrYs)
    }

    const el = ref.current
    const opts: uPlot.Options = {
      width: el.clientWidth || 600,
      height: 160,
      scales: { x: { time: false }, y: {}, ...(hasHr ? { hr: {} } : {}) },
      legend: { show: false },
      axes,
      series,
    }
    const plot = new uPlot(opts, data, el)
    // Reajusta a largura quando o container/janela muda de tamanho.
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth
      if (w > 0) plot.setSize({ width: w, height: 160 })
    })
    ro.observe(el)
    return () => { ro.disconnect(); plot.destroy() }
  }, [streams, ftp, hasHr])

  return (
    <div>
      <div ref={ref} aria-label="Perfil executado" />
      <ChartLegend hasHr={hasHr} />
    </div>
  )
}

export function IntensityProfile({ segments, streams, ftp }: { segments: Segment[]; streams?: WorkoutStreams | null; ftp: number }) {
  if (streams && streams.power.length > 0) return <StreamPlot streams={streams} ftp={ftp} />
  if (segments.length > 0) return <PlannedSvg segments={segments} />
  return <div className="text-xs text-slate-400">Sem dados de intensidade.</div>
}
