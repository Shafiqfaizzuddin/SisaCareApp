import { describe, expect, it } from 'vitest'
import type { FusedWasteObject } from '../../types'
import { categoryForItems, suggestedItems } from './campus-workflow'

function detection(name: string, category: FusedWasteObject['category'], known = true): FusedWasteObject {
  return {
    name, display_name: name, category,
    category_source: known ? 'mapping' : 'vlm', source: 'vlm',
    confidence: null, confidence_level: 'medium', supported_by_vlm: false,
    bounding_box: null, material: known ? 'Plastic' : 'Unknown',
    recyclable: category === 'Recyclable Waste', rule_known: known,
  }
}

describe('campus category routing', () => {
  it('does not treat a mixed image as wholly recyclable', () => {
    const items = suggestedItems([
      detection('Plastic Bottle', 'Recyclable Waste'),
      detection('Food Wrapper', 'Non-Recyclable'),
    ])
    expect(items.map((item) => item.category)).toEqual([
      'Recyclable Waste', 'Non-Recyclable Waste',
    ])
    expect(categoryForItems(items)).toBe('Non-Recyclable Waste')
  })

  it('routes bulky waste to reporting and requires uncertain item confirmation', () => {
    expect(categoryForItems(suggestedItems([detection('Mattress', 'Bulky Waste')]))).toBe('Bulky Waste')
    const uncertain = suggestedItems([detection('Unknown object', 'Recyclable Waste', false)])
    expect(categoryForItems(uncertain)).toBeNull()
    uncertain[0].category = 'Non-Recyclable Waste'
    expect(categoryForItems(uncertain)).toBe('Non-Recyclable Waste')
  })
})
