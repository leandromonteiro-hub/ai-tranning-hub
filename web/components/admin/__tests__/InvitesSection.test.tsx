import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { InvitesSection } from '@/components/admin/InvitesSection'
import { useInvites } from '@/lib/hooks'
import { apiFetch } from '@/lib/api'

vi.mock('@/lib/hooks', () => ({ useInvites: vi.fn() }))
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }))

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response

beforeEach(() => vi.clearAllMocks())

describe('InvitesSection', () => {
  it('lista códigos com status livre/usado', () => {
    ;(useInvites as Mock).mockReturnValue({
      data: [
        { code: 'ABCD2345', used_by_email: null, used_at: null, created_at: '2026-07-06T10:00:00Z' },
        { code: 'WXYZ7890', used_by_email: 'ana@x.com', used_at: '2026-07-06T11:00:00Z', created_at: '2026-07-06T09:00:00Z' },
      ],
      isLoading: false, mutate: vi.fn(),
    })
    render(<InvitesSection />)
    expect(screen.getByText('ABCD2345')).toBeInTheDocument()
    expect(screen.getByText('Livre')).toBeInTheDocument()
    expect(screen.getByText('ana@x.com')).toBeInTheDocument()
  })

  it('gerar convites chama o POST e revalida', async () => {
    const mutate = vi.fn()
    ;(useInvites as Mock).mockReturnValue({ data: [], isLoading: false, mutate })
    ;(apiFetch as Mock).mockResolvedValue(jsonRes([{ code: 'NEW12345' }], 201))
    render(<InvitesSection />)
    fireEvent.click(screen.getByRole('button', { name: /Gerar 5 convites/ }))
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('admin/invites', expect.objectContaining({ method: 'POST' })))
    expect(mutate).toHaveBeenCalled()
  })
})
