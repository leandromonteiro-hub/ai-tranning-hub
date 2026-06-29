import { describe, expect, it } from 'vitest'
import { nameById } from '@/lib/admin'
import type { Athlete } from '@/lib/types'

const a = (id: string, full_name: string): Athlete => ({
  id, full_name, email: `${id}@x.com`, role: 'ATHLETE', tenant_id: 't', is_active: true, created_at: '',
})

describe('nameById', () => {
  it('mapeia id → nome', () => {
    const m = nameById([a('1', 'Leandro'), a('2', 'Maria')])
    expect(m['1']).toBe('Leandro')
    expect(m['2']).toBe('Maria')
    expect(m['x']).toBeUndefined()
  })
  it('lista vazia → mapa vazio', () => {
    expect(nameById([])).toEqual({})
  })
})
