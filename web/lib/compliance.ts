export type CardStatus = 'completed' | 'planned' | 'adjusted' | 'rest'

export function cardStatus(input: { hasCompleted: boolean; hasAdjustment: boolean; isRest: boolean }): CardStatus {
  if (input.isRest) return 'rest'
  if (input.hasCompleted) return 'completed'
  if (input.hasAdjustment) return 'adjusted'
  return 'planned'
}

const COLORS: Record<CardStatus, string> = {
  completed: '#22c55e',
  planned: '#cbd5e1',
  adjusted: '#8b5cf6',
  rest: '#e2e8f0',
}
export function statusColor(status: CardStatus): string {
  return COLORS[status]
}
