import type { WasteCategory } from '../../types'

export interface WasteCategoryOption {
  value: WasteCategory
  label: string
  description: string
}

export const wasteCategoryOptions: WasteCategoryOption[] = [
  {
    value: 'household',
    label: 'Household waste',
    description: 'Furniture, food waste, appliances, or mixed domestic rubbish.',
  },
  {
    value: 'recyclable',
    label: 'Recyclable materials',
    description: 'Plastic, paper, glass, metal, or reusable materials.',
  },
  {
    value: 'construction_debris',
    label: 'Construction debris',
    description: 'Concrete, timber, tiles, soil, or renovation materials.',
  },
  {
    value: 'other',
    label: 'Other',
    description: 'Waste that does not match the listed categories.',
  },
]
