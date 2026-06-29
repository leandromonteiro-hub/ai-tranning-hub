import type { FtpPoint } from '@/lib/types'

// --- Estado de forma (TSB) — portado do intelligence_view do Streamlit ---
export type Tone = 'pos' | 'mut' | 'warn' | 'neg'

export function formReading(tsb: number): string {
  if (tsb >= 15) return 'Descansado — pico de forma'
  if (tsb >= 5) return 'Fresco — pronto para treinar forte'
  if (tsb >= -10) return 'Equilibrado — em forma'
  if (tsb >= -30) return 'Carga produtiva — fatigado'
  return 'Muito fatigado — priorize recuperação'
}

export function formTone(tsb: number): Tone {
  if (tsb >= 5) return 'pos'
  if (tsb >= -10) return 'mut'
  if (tsb >= -30) return 'warn'
  return 'neg'
}

export const TONE_TEXT: Record<Tone, string> = {
  pos: 'text-emerald-600 dark:text-emerald-400',
  mut: 'text-slate-600 dark:text-slate-300',
  warn: 'text-amber-600 dark:text-amber-400',
  neg: 'text-red-600 dark:text-red-400',
}

export function richnessLabel(score: number): string {
  if (score >= 0.75) return 'alta'
  if (score >= 0.4) return 'média'
  return 'baixa'
}

// --- Shapes do twin_seed (parciais; só o que a tela usa) ---
export type IntensitySplit = { label?: string; z1_pct?: number; z2_pct?: number; z3_pct?: number }
export type Block = { block_type?: string; evidence?: string; start?: string; end?: string }
export type DataRichness = { score?: number; label?: string; n_workouts?: number; years_covered?: number }
export type TwinSeed = {
  intensity_split?: IntensitySplit
  power_curve_bests?: Record<string, number>
  best_marks?: Record<string, number>
  block_summary?: Block[]
  data_richness?: DataRichness
}

/** FTP atual = ftp_watts do registro mais recente (já vêm ordenados por valid_from). */
export function currentFtp(ftps: FtpPoint[]): number | null {
  return ftps.length ? ftps[ftps.length - 1].ftp_watts : null
}

/** Colapsa o histórico de FTP a um registro por período (valid_from), ordenado. */
export function ftpByPeriod(ftps: FtpPoint[]): FtpPoint[] {
  const byStart = new Map<string, FtpPoint>()
  for (const f of ftps) byStart.set(f.valid_from, f)
  return [...byStart.values()].sort((a, b) => a.valid_from.localeCompare(b.valid_from))
}

/** Curva de potência: power_curve_bests, com fallback para best_marks. */
export function powerCurve(twin: TwinSeed | null): Record<string, number> | null {
  return twin?.power_curve_bests ?? twin?.best_marks ?? null
}
