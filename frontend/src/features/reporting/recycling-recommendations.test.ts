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
      { name: 'Plastic Bottle', material: 'plastic', stationMaterialKey: 'Plastic', category: 'Recyclable Waste' },
      { name: 'Paper', material: 'Paper', stationMaterialKey: 'Paper', category: 'Recyclable Waste' },
    ], { latitude: 6.4, longitude: 100.2 })
    expect(result.map(entry => entry.point.id)).toEqual(['near', 'far'])
    expect(result[0].matchedMaterials).toEqual(['Plastic'])
    expect(result[0].unmatchedMaterials).toEqual(['Paper'])
    expect(result[1].unmatchedMaterials).toEqual([])
  })

  it('returns no recommendation when no point accepts the material', () => {
    expect(recommendPoints(points, [{ name: 'Can', material: 'Aluminium', category: 'Recyclable Waste' }],
      { latitude: 6.4, longitude: 100.2 })).toEqual([])
  })

  it('requires answered condition questions before recommending an accepted point', () => {
    const item = { name: 'Plastic Bottle', material: 'Plastic', stationMaterialKey: 'Plastic', category: 'Recyclable Waste' as const,
      questions: [{ key: 'hazardous_contents', prompt: 'Hazardous contents?' }, { key: 'empty_and_clean', prompt: 'Empty and clean?' }],
      condition_answers: { empty_and_clean: true } }
    const origin = { latitude: 6.4, longitude: 100.2 }
    expect(recommendPoints(points, [item], origin)).toEqual([])
    expect(recommendPoints(points, [{ ...item, condition_answers: { empty_and_clean: true, hazardous_contents: false } }], origin)
      .map(entry => entry.point.id)).toEqual(['near', 'far'])
  })
  it('does not guess station acceptance from a material alone', () => {
    const origin = { latitude: 6.4, longitude: 100.2 }
    expect(recommendPoints(points, [{ name: 'Bottle', material: 'Plastic', category: 'Recyclable Waste' }], origin)).toEqual([])
    expect(recommendPoints(points, [{ name: 'Battery', material: 'Metal', stationMaterialKey: 'Plastic', category: 'Hazardous Waste' }], origin)).toEqual([])
  })
})
