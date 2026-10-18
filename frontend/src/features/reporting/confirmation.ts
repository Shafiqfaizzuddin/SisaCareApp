import type { CampusWasteCategory, FlorenceDetection } from '../../types'
import type { ConfirmedItem } from './campus-workflow'

export type ReviewDisposition = 'waste' | 'background' | 'removed' | 'attached_component' | 'needs_confirmation'
export type ComponentRelation = 'attached' | 'detached' | 'unclear' | null

export interface ReviewedItem extends ConfirmedItem {
  id: string
  sourceDetectionId: string | null
  originalLabel: string | null
  status: ReviewDisposition
  componentRelation: ComponentRelation
  quantity?: number
  handlingGuidance?: string
  confirmationReason?: string | null
  ruleId?: string
  stationMaterialKey?: string | null
  classificationSource?: 'rule' | 'user_confirmed'
}

export function isCap(label: string): boolean {
  return ['cap', 'bottle cap', 'plastic bottle cap'].includes(label.trim().toLowerCase().replaceAll('_', ' '))
}

export function initialItem(detection: FlorenceDetection): ReviewedItem {
  const cap = isCap(detection.display_name)
  return {
    id: detection.id, sourceDetectionId: detection.id, originalLabel: detection.label,
    name: detection.display_name, material: detection.material,
    category: detection.suggested_category ?? '',
    status: cap ? 'needs_confirmation' : detection.review_status === 'likely_waste' ? 'waste' : detection.review_status,
    componentRelation: cap ? 'unclear' : null,
    condition_answers: {}, questions: detection.questions ?? [],
    handlingGuidance: detection.recommended_handling,
    confirmationReason: detection.confirmation_question ?? detection.confirmation_reason,
    ruleId: detection.rule_id ?? undefined,
    stationMaterialKey: detection.station_material_key,
    classificationSource: detection.classification_source,
  }
}

export function groupReviewedItems(items: ReviewedItem[]): ReviewedItem[][] {
  const groups = new Map<string, ReviewedItem[]>()
  for (const item of items) {
    // Group for display only. Each review and source detection remains distinct.
    const key = [item.name.trim().toLocaleLowerCase(), item.material.trim().toLocaleLowerCase(), item.status, item.componentRelation ?? ''].join('|')
    const group = groups.get(key) ?? []
    group.push(item)
    groups.set(key, group)
  }
  return [...groups.values()]
}

export function categoriesForItems(items: ReviewedItem[]): CampusWasteCategory[] {
  const order: CampusWasteCategory[] = ['Hazardous Waste', 'Bulky Waste', 'Non-Recyclable Waste', 'Recyclable Waste']
  return order.filter((category) => items.some((item) => item.status === 'waste' && item.category === category))
}
