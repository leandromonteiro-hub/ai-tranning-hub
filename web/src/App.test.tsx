import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { App } from './App'

describe('App', () => {
  it('renderiza o shell com o título Calendário', () => {
    render(<App />)
    expect(screen.getByText('ATHLETE HUB')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Calendário' })).toBeInTheDocument()
  })
})
