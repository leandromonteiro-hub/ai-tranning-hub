import type { Segment } from '@/lib/structure'
import { zoneColor } from '@/lib/zones'

export function IntensityThumbnail({ segments, height = 28 }: { segments: Segment[]; height?: number }) {
  const total = segments.reduce((a, s) => a + s.durationS, 0) || 1
  const maxW = Math.max(1, ...segments.map((s) => s.highW ?? 0))
  let x = 0
  return (
    <svg width="100%" height={height} viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" aria-hidden="true">
      {segments.map((s, i) => {
        const w = (s.durationS / total) * 100
        const h = ((s.highW ?? maxW * 0.4) / maxW) * height
        const rect = <rect key={i} x={x} y={height - h} width={w} height={h} fill={zoneColor(s.zone)} />
        x += w
        return rect
      })}
    </svg>
  )
}
