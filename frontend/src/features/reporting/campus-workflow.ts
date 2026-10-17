import type { CampusWasteCategory, FusedWasteObject } from '../../types'

export type ConfirmedItem = {
  name: string
  category: CampusWasteCategory | ''
  material: string
  condition_answers?: Record<string, boolean>
  questions?: Array<{ key: string; prompt: string }>
}

export function suggestedItems(detections: FusedWasteObject[]): ConfirmedItem[] {
  return detections.map((detection) => ({
    name: detection.display_name,
    material: detection.material || 'Unknown',
    category: detection.rule_known && detection.category_source === 'mapping'
      ? detection.category === 'Non-Recyclable' ? 'Non-Recyclable Waste'
        : detection.category === 'Recyclable Waste' || detection.category === 'Bulky Waste'
          ? detection.category : ''
      : '',
  }))
}

export function categoryForItems(items: ConfirmedItem[]): CampusWasteCategory | null {
  if (items.length === 0 || items.some((item) => !item.name.trim() || !item.category)) return null
  if (items.some((item) => item.category === 'Hazardous Waste')) return 'Hazardous Waste'
  if (items.some((item) => item.category === 'Bulky Waste')) return 'Bulky Waste'
  if (items.every((item) => item.category === 'Recyclable Waste')) return 'Recyclable Waste'
  return 'Non-Recyclable Waste'
}
