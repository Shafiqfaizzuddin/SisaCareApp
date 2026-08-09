import {
  CircleHelp,
  Hammer,
  House,
  Recycle,
  type LucideIcon,
} from 'lucide-react'
import type { EducationalContent, WasteCategory } from '../../types'

const categoryIcons: Record<WasteCategory, LucideIcon> = {
  household: House,
  recyclable: Recycle,
  construction_debris: Hammer,
  other: CircleHelp,
}

export function WasteGuideCard({ topic }: { topic: EducationalContent }) {
  const Icon = categoryIcons[topic.category]

  return (
    <article className="guide-card">
      <div className={`guide-card__icon guide-card__icon--${topic.category}`}>
        <Icon size={22} />
      </div>
      <h2>{topic.title}</h2>
      <p>{topic.content}</p>
      {topic.imageUrl && <img src={topic.imageUrl} alt="" />}
    </article>
  )
}
