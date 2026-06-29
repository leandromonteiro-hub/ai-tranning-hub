import { powerToZone } from '@/lib/zones'

export function streamToBars(power: Array<number | null>, ftp: number): Array<{ value: number; zone: number }> {
  return power.map((p) => {
    const v = p ?? 0
    return { value: v, zone: powerToZone(v, ftp) }
  })
}
