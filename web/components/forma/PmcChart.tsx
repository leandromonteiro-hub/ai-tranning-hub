"use client";
import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { LoadMetric } from '@/lib/types'

const COLORS = { ctl: '#2563eb', atl: '#f97316', tsb: '#10b981' }

export function PmcChart({ series }: { series: LoadMetric[] }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || series.length === 0) return
    const el = ref.current
    const xs = series.map((d) => Date.parse(d.metric_date) / 1000)
    const opts: uPlot.Options = {
      width: el.clientWidth || 600,
      height: 240,
      legend: { show: true },
      scales: { x: { time: true } },
      axes: [{}, { size: 44 }],
      series: [
        {},
        { label: 'Fitness (CTL)', stroke: COLORS.ctl, width: 2 },
        { label: 'Fadiga (ATL)', stroke: COLORS.atl, width: 1.5 },
        { label: 'Forma (TSB)', stroke: COLORS.tsb, width: 1.5 },
      ],
    }
    const data: uPlot.AlignedData = [
      xs,
      series.map((d) => d.ctl),
      series.map((d) => d.atl),
      series.map((d) => d.tsb),
    ]
    const plot = new uPlot(opts, data, el)
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth
      if (w > 0) plot.setSize({ width: w, height: 240 })
    })
    ro.observe(el)
    return () => { ro.disconnect(); plot.destroy() }
  }, [series])

  if (series.length === 0) return <div className="text-sm text-slate-400">Sem dados de carga ainda.</div>
  return <div ref={ref} aria-label="Tendência PMC (CTL/ATL/TSB)" />
}
