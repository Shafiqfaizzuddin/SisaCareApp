import type { WasteCategory } from '../../types'

export interface WasteCategoryOption {
  value: WasteCategory
  label: string
  description: string
}

export const wasteCategoryOptions: WasteCategoryOption[] = [
  { value: 'Recyclable Waste', label: 'Recyclable Waste', description: 'Confirmed recyclable materials.' },
  { value: 'Non-Recyclable Waste', label: 'Non-Recyclable Waste', description: 'General or mixed waste requiring appropriate collection.' },
  { value: 'Bulky Waste', label: 'Bulky Waste', description: 'Large items routed to a waste report.' },
  { value: 'Hazardous Waste', label: 'Hazardous Waste', description: 'Items requiring reviewed handling and staff response.' },
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
