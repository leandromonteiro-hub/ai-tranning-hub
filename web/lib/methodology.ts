// Recortes do twin_seed usados na página de Metodologia.
export type Taper = {
  race_date: string
  ctl_start: number
  ctl_race: number
  tsb_race: number
  atl_race: number
  evidence: string
  weekly_tss_trend?: number[]
}
export type PeriodizationSummary = {
  n_blocks?: number
  recovery_blocks?: number
  meso_length_days_typical?: number
}
export type CoachTerm = [string, number]
export type MethodologyTwin = {
  periodization_summary?: PeriodizationSummary
  tapers?: Taper[]
  coach_terms?: CoachTerm[]
  intensity_split?: { label?: string; z1_pct?: number; z2_pct?: number; z3_pct?: number }
}

/** Mediana (lista vazia → null). */
export function median(xs: number[]): number | null {
  if (xs.length === 0) return null
  const s = [...xs].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2
}

export type MethodologySummary = {
  mesoLengthDays: number | null
  nBlocks: number | null
  recoveryBlocks: number | null
  recoveryEveryN: number | null
  taperCount: number
  medianTsbRace: number | null
  medianCtlGain: number | null
}

/** Resumo derivado dos critérios do treinador (periodização + taper). */
export function methodologySummary(twin: MethodologyTwin | null): MethodologySummary {
  const ps = twin?.periodization_summary ?? {}
  const tapers = twin?.tapers ?? []
  const nBlocks = ps.n_blocks ?? null
  const recoveryBlocks = ps.recovery_blocks ?? null
  return {
    mesoLengthDays: ps.meso_length_days_typical ?? null,
    nBlocks,
    recoveryBlocks,
    recoveryEveryN: nBlocks && recoveryBlocks ? Math.round(nBlocks / recoveryBlocks) : null,
    taperCount: tapers.length,
    medianTsbRace: median(tapers.map((t) => t.tsb_race)),
    medianCtlGain: median(tapers.map((t) => t.ctl_race - t.ctl_start)),
  }
}
