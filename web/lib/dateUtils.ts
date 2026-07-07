/** Data de hoje em ISO (YYYY-MM-DD), no fuso LOCAL do cliente (não UTC).
 *  Usar UTC fazia o "hoje" virar amanhã após ~21h no horário do Brasil (UTC-3),
 *  pulando o treino da noite no dashboard/calendário. */
export function todayIso(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
