import { pctToZone } from '@/lib/zones'

export type StepEl = {
  intensity: string
  duration_s: number
  target?: { type: string; low?: number | null; high?: number | null }
  note?: string
}
export type RepeatEl = { count: number; steps: StepEl[] }
export type WorkoutStructure = { name?: string; elements?: Array<StepEl | RepeatEl>; ftp_watts?: number | null }
export type Segment = { durationS: number; lowW: number | null; highW: number | null; zone: number; intensity: string }

const LABELS: Record<string, string> = { warmup: 'Warm up', active: 'Active', rest: 'Recovery', cooldown: 'Cool Down' }

function flatten(structure: WorkoutStructure | null): StepEl[] {
  if (!structure?.elements) return []
  const out: StepEl[] = []
  for (const el of structure.elements) {
    if ('steps' in el && Array.isArray((el as RepeatEl).steps)) {
      const rep = el as RepeatEl
      for (let i = 0; i < rep.count; i++) out.push(...rep.steps)
    } else {
      out.push(el as StepEl)
    }
  }
  return out
}

function toSegment(step: StepEl, ftp: number): Segment {
  const t = step.target
  const isOpen = !t || t.type === 'open' || (t.low == null && t.high == null)
  const lowW = isOpen || t?.low == null ? null : Math.round(t.low * ftp)
  const highW = isOpen || t?.high == null ? null : Math.round(t.high * ftp)
  const mid = isOpen ? 0 : ((t?.low ?? t?.high ?? 0) + (t?.high ?? t?.low ?? 0)) / 2
  return { durationS: step.duration_s, lowW, highW, zone: isOpen ? 1 : pctToZone(mid), intensity: step.intensity }
}

export function structureToSegments(structure: WorkoutStructure | null, ftpFallback = 250): Segment[] {
  const ftp = structure?.ftp_watts ?? ftpFallback
  return flatten(structure).map((s) => toSegment(s, ftp))
}

export function structureToSteps(structure: WorkoutStructure | null, ftpFallback = 250) {
  const ftp = structure?.ftp_watts ?? ftpFallback
  return flatten(structure).map((s) => {
    const seg = toSegment(s, ftp)
    return { label: LABELS[s.intensity] ?? s.intensity, durationS: seg.durationS, lowW: seg.lowW, highW: seg.highW, zone: seg.zone }
  })
}
