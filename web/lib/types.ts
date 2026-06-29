import type { WorkoutStructure } from '@/lib/structure'

export type PlannedWorkout = {
  id: string; planned_date: string; name: string; workout_type: string
  planned_duration_s: number | null; planned_tss: number | null
  description: string | null; structure: WorkoutStructure | null
  adjustment: Record<string, unknown> | null
}
export type CompletedWorkout = {
  id: string; workout_date: string; name: string | null; workout_type: string
  duration_s: number | null; distance_m: number | null; tss: number | null
  intensity_factor: number | null; avg_power: number | null; normalized_power: number | null
  avg_hr: number | null; kj: number | null; elevation_gain_m: number | null; notes: string | null
}
export type RaceMarker = { id: string; name: string; race_date: string; days_until: number }
export type CalendarDay = { date: string; planned: PlannedWorkout[]; completed: CompletedWorkout[]; races: RaceMarker[] }
export type WeekSummary = {
  week_start: string; ctl: number | null; atl: number | null; tsb: number | null
  total_duration_s: number; total_tss: number; total_distance_m: number; total_elevation_m: number; total_kj: number
}
export type CalendarResponse = { days: CalendarDay[]; weeks: WeekSummary[] }
export type WorkoutStreams = {
  workout_id: string; n_points: number
  time_s: Array<number | null>; power: Array<number | null>; heart_rate: Array<number | null>
  cadence: Array<number | null>; altitude: Array<number | null>
}

// --- Forma & Carga (inteligência + PMC) ---
export type FtpPoint = { ftp_watts: number; valid_from: string; valid_to: string | null; method: string | null }
export type FormState = { metric_date: string; ctl: number; atl: number; tsb: number }
export type AthleteIntelligence = {
  twin_seed: Record<string, unknown> | null
  ftp_history: FtpPoint[]
  form: FormState | null
}
export type LoadMetric = {
  metric_date: string; daily_tss: number; ctl: number; atl: number; tsb: number
  monotony: number | null; strain: number | null
}

// --- Recomendações (IA do dia) ---
export type Evidence = { evidence_type: string; description: string; similarity: number | null }
export type Recommendation = {
  id: string; target_date: string | null; kind: string; summary: string
  physiological_objective: string | null; block_relation: string | null; rationale: string | null
  adjust_if_tired: string | null; adjust_if_less_time: string | null
  payload: Record<string, unknown> | null
  risk_level: string; risk_flags: Record<string, unknown> | null
  confidence: number | null; confidence_rationale: string | null
  decision: string; created_at: string; evidence: Evidence[]
}
