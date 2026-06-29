/**
 * Decisão pura do polling de um job assíncrono (estado Celery + tentativa).
 * Porta o job_poll do Streamlit. O chamador faz o GET/sleep e alimenta o state.
 *   done     → SUCCESS
 *   failed   → FAILURE
 *   giveup   → não-terminal mas atingiu o limite de tentativas
 *   continue → seguir consultando
 */
export type PollDecision = 'done' | 'failed' | 'giveup' | 'continue'

export function pollDecision(state: string, attempt: number, maxAttempts: number): PollDecision {
  if (state === 'SUCCESS') return 'done'
  if (state === 'FAILURE') return 'failed'
  if (attempt >= maxAttempts) return 'giveup'
  return 'continue'
}
