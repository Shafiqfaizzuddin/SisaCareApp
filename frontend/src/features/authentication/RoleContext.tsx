import {
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { UserRole } from '../../types'
import { demoAdmin, demoMember } from './member-data'
import { RoleContext, type RoleContextValue } from './role-context'

export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<UserRole>('guest')
  const [memberPoints, setMemberPoints] = useState(demoMember.points)
  const [memberValidReports, setMemberValidReports] = useState(
    demoMember.validReports ?? 0,
  )

  const value = useMemo<RoleContextValue>(() => {
    const user =
      role === 'user'
        ? {
            ...demoMember,
            points: memberPoints,
            validReports: memberValidReports,
          }
        : role === 'admin'
          ? demoAdmin
          : null

    return {
      role,
      user,
      signInAs: (nextRole) => setRole(nextRole),
      signOut: () => setRole('guest'),
      rewardMember: (points, validReport = false) => {
        setMemberPoints((current) => current + points)
        if (validReport) {
          setMemberValidReports((current) => current + 1)
        }
      },
    }
  }, [memberPoints, memberValidReports, role])

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>
}
