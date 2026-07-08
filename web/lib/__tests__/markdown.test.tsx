import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '@/lib/markdown'

function show(md: string) {
  return render(<div data-testid="md">{renderMarkdown(md)}</div>)
}

describe('renderMarkdown', () => {
  it('título ## vira heading, não texto literal', () => {
    show('## Objetivo fisiológico')
    expect(screen.getByText('Objetivo fisiológico')).toBeInTheDocument()
    expect(screen.getByTestId('md').textContent).not.toContain('##')
  })

  it('**negrito** vira <strong>', () => {
    show('Isto é **importante** aqui')
    const strong = screen.getByText('importante')
    expect(strong.tagName).toBe('STRONG')
    expect(screen.getByTestId('md').textContent).not.toContain('**')
  })

  it('linhas "- " viram itens de lista', () => {
    show('- primeiro\n- segundo')
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('primeiro')
  })

  it('texto puro sem markdown vira um parágrafo', () => {
    show('Apenas um texto simples.')
    expect(screen.getByText('Apenas um texto simples.').tagName).toBe('P')
  })

  it('--- não aparece como texto literal', () => {
    show('Antes\n---\nDepois')
    expect(screen.getByTestId('md').textContent).not.toContain('---')
  })

  it('vazio/null retorna nada', () => {
    const { container } = render(<div>{renderMarkdown(null)}</div>)
    expect(container.querySelector('div')?.textContent).toBe('')
  })
})
