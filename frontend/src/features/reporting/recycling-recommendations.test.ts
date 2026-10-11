import { describe, expect, it } from 'vitest'
import { recommendPoints } from './recycling-recommendations'
import type { RecyclingPoint } from './recycling-points'

const points: RecyclingPoint[] = [
  { id: 'far', name: 'Far point', latitude: 6.41, longitude: 100.2, accepted_materials: ['Plastic', 'Paper'], description: '', active: true },
  { id: 'near', name: 'Near point', latitude: 6.4001, longitude: 100.2, accepted_materials: ['Plastic'], description: '', active: true },
  { id: 'inactive', name: 'Inactive point', latitude: 6.4, longitude: 100.2, accepted_materials: ['Paper'], description: '', active: false },
  { id: 'wrong', name: 'Wrong point', latitude: 6.4, longitude: 100.2, accepted_materials: ['Glass'], description: '', active: true },
]

describe('recycling recommendations', () => {
  it('shows only active matching points, ranks by straight-line distance, and labels partial matches', () => {
    const result = recommendPoints(points, [
      { name: 'Bottle', material: 'plastic', category: 'Recyclable Waste' },
      { name: 'Sheet', material: 'Paper', category: 'Recyclable Waste' },
    ], { latitude: 6.4, longitude: 100.2 })
    expect(result.map(entry => entry.point.id)).toEqual(['near', 'far'])
    expect(result[0].matchedMaterials).toEqual(['plastic'])
    expect(result[0].unmatchedMaterials).toEqual(['Paper'])
    expect(result[1].unmatchedMaterials).toEqual([])
  })

  it('returns no recommendation when no point accepts the material', () => {
    expect(recommendPoints(points, [{ name: 'Can', material: 'Aluminium', category: 'Recyclable Waste' }],
      { latitude: 6.4, longitude: 100.2 })).toEqual([])
  })
})
