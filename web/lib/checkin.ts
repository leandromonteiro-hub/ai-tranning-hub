export type CheckinForm = {
  sleep_hours: string
  resting_hr: string
  hrv_ms: string
  fatigue: number
  soreness: number
  mood: number
  motivation: number
  injury_flag: boolean
  comment: string
}

/** Corpo do POST /metrics/recovery (hrv_ms vazio/0 → null). */
export function recoveryBody(f: CheckinForm, today: string): Record<string, unknown> {
  const hrv = f.hrv_ms.trim() === '' ? 0 : Number(f.hrv_ms)
  return {
    metric_date: today,
    sleep_hours: f.sleep_hours.trim() === '' ? null : Number(f.sleep_hours),
    resting_hr: f.resting_hr.trim() === '' ? null : Number(f.resting_hr),
    hrv_ms: hrv > 0 ? hrv : null,
  }
}

/** Corpo do POST /metrics/subjective (comment vazio → null). */
export function subjectiveBody(f: CheckinForm, today: string): Record<string, unknown> {
  return {
    metric_date: today,
    fatigue: f.fatigue,
    soreness: f.soreness,
    mood: f.mood,
    motivation: f.motivation,
    injury_flag: f.injury_flag,
    comment: f.comment.trim() === '' ? null : f.comment.trim(),
  }
}
