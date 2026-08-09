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
  const { authLoading, role } = useRole()

  if (authLoading) {
    return (
      <main className="auth-loading" aria-live="polite">
        <span className="auth-loading__spinner" aria-hidden="true" />
        <p>Checking your session...</p>
      </main>
    )
  }

  if (!allow.includes(role)) {
    return <Navigate to={redirectTo} replace />
  }

  return children
}
