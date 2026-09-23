import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useRole } from '../../features/authentication/useRole'
import type { UserRole } from '../../types'

interface RoleGuardProps {
  allow: UserRole[]
  redirectTo: string
  children: ReactNode
}

export function RoleGuard({ allow, redirectTo, children }: RoleGuardProps) {
  const { isAuthLoading, role } = useRole()

  if (isAuthLoading) {
    return <p className="empty-state empty-state--page">Restoring session...</p>
  }

  if (!allow.includes(role)) {
    return <Navigate to={redirectTo} replace />
  }

  return children
}
