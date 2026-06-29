import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CheckinView } from '@/components/checkin/CheckinView'

describe('CheckinView', () => {
  it('renderiza o form de check-in', () => {
    render(<CheckinView />)
    expect(screen.getByText('📝 Check-in diário')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Registrar check-in/ })).toBeInTheDocument()
    expect(screen.getByText(/Fadiga/)).toBeInTheDocument()
  })
})
