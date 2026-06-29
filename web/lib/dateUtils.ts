/** Data de hoje em ISO (YYYY-MM-DD), lida do relógio na borda do cliente. */
export function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}
