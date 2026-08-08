import { Leaf } from 'lucide-react'
import { Link } from 'react-router-dom'

interface BrandProps {
  compact?: boolean
}

export function Brand({ compact = false }: BrandProps) {
  return (
    <Link className="brand" to="/" aria-label="SisaCare.AI home">
      <span className="brand__mark" aria-hidden="true">
        <Leaf size={19} strokeWidth={2.4} />
      </span>
      <span className="brand__name">
        SisaCare<span>.AI</span>
      </span>
      {!compact && <span className="brand__descriptor">Community reporting</span>}
    </Link>
  )
}
