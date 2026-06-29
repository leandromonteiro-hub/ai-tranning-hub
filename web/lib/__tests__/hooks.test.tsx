import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useCalendar } from '@/lib/hooks'

afterEach(() => vi.restoreAllMocks())

describe('useCalendar', () => {
  it('busca o proxy /calendar e retorna days', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ days: [{ date: '2026-05-12', planned: [], completed: [], races: [] }], weeks: [] }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    const { result } = renderHook(() => useCalendar('2026-05-11', '2026-05-17'))
    await waitFor(() => expect(result.current.data).toBeDefined())
    expect(result.current.data?.days[0].date).toBe('2026-05-12')
    // confirma que passou pelo proxy BFF
    const calledUrl = (globalThis.fetch as unknown as { mock: { calls: string[][] } }).mock.calls[0][0]
    expect(String(calledUrl)).toContain('/api/proxy/calendar')
  })
})
