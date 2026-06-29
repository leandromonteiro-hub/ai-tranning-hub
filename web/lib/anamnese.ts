import type { AthleteProfile } from '@/lib/types'

/** Formulário da anamnese: tudo string (inputs) + 2 booleanos. */
export type AnamneseForm = {
  birth_date: string; sex: string; weight_kg: string; height_cm: string
  max_hr: string; resting_hr: string; primary_discipline: string; years_training: string
  goals: string; weekly_hours: string; weekly_days: string
  injury_history: string; medical_conditions: string
  has_power_meter: boolean; has_hr_monitor: boolean
}

const numOrNull = (s: string): number | null => (s.trim() === '' ? null : Number(s))
const strOrNull = (s: string): string | null => (s.trim() === '' ? null : s.trim())

/** Converte o formulário no corpo do PUT /athletes/me/profile (vazio → null). */
export function toProfilePayload(f: AnamneseForm): Record<string, unknown> {
  return {
    birth_date: strOrNull(f.birth_date),
    sex: strOrNull(f.sex),
    weight_kg: numOrNull(f.weight_kg),
    height_cm: numOrNull(f.height_cm),
    max_hr: numOrNull(f.max_hr),
    resting_hr: numOrNull(f.resting_hr),
    primary_discipline: strOrNull(f.primary_discipline),
    years_training: numOrNull(f.years_training),
    goals: strOrNull(f.goals),
    weekly_hours: numOrNull(f.weekly_hours),
    weekly_days: numOrNull(f.weekly_days),
    injury_history: strOrNull(f.injury_history),
    medical_conditions: strOrNull(f.medical_conditions),
    has_power_meter: f.has_power_meter,
    has_hr_monitor: f.has_hr_monitor,
  }
}

/** Semeia o formulário a partir do perfil carregado (null → vazio). */
export function fromProfile(p: AthleteProfile | null | undefined): AnamneseForm {
  const s = (v: string | null | undefined) => v ?? ''
  const n = (v: number | null | undefined) => (v == null ? '' : String(v))
  return {
    birth_date: s(p?.birth_date), sex: s(p?.sex),
    weight_kg: n(p?.weight_kg), height_cm: n(p?.height_cm),
    max_hr: n(p?.max_hr), resting_hr: n(p?.resting_hr),
    primary_discipline: s(p?.primary_discipline), years_training: n(p?.years_training),
    goals: s(p?.goals), weekly_hours: n(p?.weekly_hours), weekly_days: n(p?.weekly_days),
    injury_history: s(p?.injury_history), medical_conditions: s(p?.medical_conditions),
    has_power_meter: !!p?.has_power_meter, has_hr_monitor: !!p?.has_hr_monitor,
  }
}
