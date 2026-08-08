import type { ReactNode } from 'react'

interface PageIntroProps {
  eyebrow?: string
  title: string
  description: string
  actions?: ReactNode
}

export function PageIntro({
  eyebrow,
  title,
  description,
  actions,
}: PageIntroProps) {
  return (
    <header className="page-intro">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        <p className="page-intro__description">{description}</p>
      </div>
      {actions && <div className="page-intro__actions">{actions}</div>}
    </header>
  )
}
