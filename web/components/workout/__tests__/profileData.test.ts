import { describe, expect, it } from 'vitest'
import { streamToBars } from '@/components/workout/profileData'

describe('streamToBars', () => {
  it('mapeia cada ponto à zona, null vira 0/zona1', () => {
    expect(streamToBars([null, 150, 300], 300)).toEqual([
      { value: 0, zone: 1 },
      { value: 150, zone: 1 },
      { value: 300, zone: 4 },
    ])
  })
})
