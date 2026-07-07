import { describe, expect, it } from 'vitest'
import { NAV_ITEMS } from '@/components/Sidebar'

describe('Sidebar NAV_ITEMS', () => {
  it('inclui o item Conexões apontando para /conexoes', () => {
    const item = NAV_ITEMS.find((i) => i.href === '/conexoes')
    expect(item).toBeDefined()
    expect(item?.label).toBe('Conexões')
  })

  it('Conexões vem logo após Importar', () => {
    const importar = NAV_ITEMS.findIndex((i) => i.href === '/importar')
    const conexoes = NAV_ITEMS.findIndex((i) => i.href === '/conexoes')
    expect(conexoes).toBe(importar + 1)
  })
})
