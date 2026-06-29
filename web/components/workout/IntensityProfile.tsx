"use client";
import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { WorkoutStreams } from '@/lib/types'
import type { Segment } from '@/lib/structure'
import { zoneColor } from '@/lib/zones'
import { streamToBars } from '@/components/workout/profileData'

function PlannedSvg({ segments }: { segments: Segment[] }) {
  const total = segments.reduce((a, s) => a + s.durationS, 0) || 1
  const maxW = Math.max(1, ...segments.map((s) => s.highW ?? 0))
  let x = 0
  return (
    <svg width="100%" height={120} viewBox="0 0 100 120" preserveAspectRatio="none" role="img" aria-label="Perfil planejado">
      {segments.map((s, i) => {
        const w = (s.durationS / total) * 100
        const h = ((s.highW ?? maxW * 0.4) / maxW) * 120
        const rect = <rect key={i} x={x} y={120 - h} width={w} height={h} fill={zoneColor(s.zone)} />
        x += w
        return rect
      })}
    </svg>
  )
}

function StreamPlot({ streams, ftp }: { streams: WorkoutStreams; ftp: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const bars = streamToBars(streams.power, ftp)
    const xs = bars.map((_, i) => i)
    const ys = bars.map((b) => b.value)
    // Coloração por zona: pinta cada ponto com a cor da sua zona via paths por-ponto.
    const opts: uPlot.Options = {
      width: ref.current.clientWidth || 600,
      height: 150,
      scales: { x: { time: false } },
      legend: { show: false },
      axes: [{ show: false }, { size: 34 }],
      series: [
        {},
        {
          stroke: '#1d4ed8',
          width: 1,
          paths: (u, sidx, i0, i1) => {
            const p = new Path2D()
            const ctx = (u as unknown as { ctx: CanvasRenderingContext2D }).ctx
            for (let i = i0; i <= i1; i++) {
              const xv = u.valToPos(u.data[0][i] as number, 'x', true)
              const yv = u.valToPos(u.data[sidx][i] as number, 'y', true)
              const y0 = u.valToPos(0, 'y', true)
              ctx.beginPath()
              ctx.strokeStyle = zoneColor(bars[i].zone)
              ctx.moveTo(xv, y0)
              ctx.lineTo(xv, yv)
              ctx.stroke()
            }
            return { stroke: p }
          },
        },
      ],
    }
    const plot = new uPlot(opts, [xs, ys], ref.current)
    return () => plot.destroy()
  }, [streams, ftp])
  return <div ref={ref} aria-label="Perfil executado" />
}

export function IntensityProfile({ segments, streams, ftp }: { segments: Segment[]; streams?: WorkoutStreams | null; ftp: number }) {
  if (streams && streams.power.length > 0) return <StreamPlot streams={streams} ftp={ftp} />
  if (segments.length > 0) return <PlannedSvg segments={segments} />
  return <div className="text-xs text-slate-400">Sem dados de intensidade.</div>
}
