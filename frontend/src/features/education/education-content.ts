import type { WasteCategory } from '../../types'

export interface EducationTopic {
  category: WasteCategory
  title: string
  description: string
  disposalTip: string
}

export const educationTopics: EducationTopic[] = [
  {
    category: 'household',
    title: 'Household waste',
    description: 'Bulky furniture, appliances, food waste, and mixed domestic items.',
    disposalTip: 'Use scheduled bulky-waste collection or an approved community facility.',
  },
  {
    category: 'recyclable',
    title: 'Recyclables',
    description: 'Clean paper, cardboard, glass, metal, and accepted plastics.',
    disposalTip: 'Separate clean materials and use a recognised recycling collection point.',
  },
  {
    category: 'construction_debris',
    title: 'Construction debris',
    description: 'Concrete, timber, tiles, soil, plasterboard, and renovation offcuts.',
    disposalTip: 'Arrange collection through a licensed construction-waste contractor.',
  },
  {
    category: 'other',
    title: 'Hazardous or unknown waste',
    description: 'Chemicals, batteries, paint, oils, and unidentified containers.',
    disposalTip: 'Do not touch or move it. Report it so trained personnel can assess the site.',
  },
]
