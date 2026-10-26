import { describe, expect, it } from 'vitest'
import { categoriesForItems, groupReviewedItems, initialItem, isCap, type ReviewedItem } from './confirmation'
import type { FlorenceDetection } from '../../types'

function detection(id: string, label: string): FlorenceDetection {
  return { id, label, name: label, display_name: label, bounding_box: { x1: 1, y1: 2, x2: 20, y2: 30 },
    confidence: null, review_status: 'likely_waste', suggested_category: 'Recyclable Waste', material: 'Plastic',
    recommended_handling: '' }
}

describe('item confirmation', () => {
  it('groups repeated labels for display without merging their detection IDs', () => {
    const items = [initialItem(detection('one', 'plastic bottle')), initialItem(detection('two', 'plastic bottle'))]
    const groups = groupReviewedItems(items)
    expect(groups).toHaveLength(1)
    expect(groups[0].map((item) => item.sourceDetectionId)).toEqual(['one', 'two'])
  })

  it('requires an explicit relationship for caps and keeps mixed categories', () => {
    const cap = initialItem(detection('cap', 'bottle cap'))
    expect(isCap(cap.name)).toBe(true)
    expect(cap.status).toBe('needs_confirmation')
    expect(cap.componentRelation).toBe('unclear')
    const items: ReviewedItem[] = [
      { ...initialItem(detection('bottle', 'plastic bottle')), category: 'Recyclable Waste', status: 'waste' },
      { ...initialItem(detection('battery', 'battery')), category: 'Hazardous Waste', status: 'waste' },
    ]
    expect(categoriesForItems(items)).toEqual(['Hazardous Waste', 'Recyclable Waste'])
  })

  it('groups ten rule-equivalent detections without changing their IDs or boxes', () => {
    const items = Array.from({ length: 10 }, (_, index) => ({
      ...initialItem(detection(`det-${index}`, index % 2 ? 'Plastic Bag' : 'Plastic Film')),
      ruleId: index % 2 ? 'COMMUNITY-PLASTIC_BAG-v1' : 'COMMUNITY-PLASTIC_FILM-v1',
      category: 'Non-Recyclable Waste' as const, status: 'waste' as const,
    }))
    const groups = groupReviewedItems(items)
    expect(groups).toHaveLength(1)
    expect(groups[0]).toHaveLength(10)
    expect(groups[0].map((item) => item.sourceDetectionId)).toEqual(items.map((item) => item.id))
  })

  it('does not merge hazardous or materially different observations', () => {
    const ordinary = { ...initialItem(detection('ordinary', 'Can')), ruleId: 'can', category: 'Recyclable Waste' as const }
    const hazardous = { ...ordinary, id: 'hazard', sourceDetectionId: 'hazard', ruleId: 'aerosol_can', category: 'Hazardous Waste' as const }
    const glass = { ...ordinary, id: 'glass', sourceDetectionId: 'glass', material: 'Glass' }
    expect(groupReviewedItems([ordinary, hazardous, glass])).toHaveLength(3)
  })
})
