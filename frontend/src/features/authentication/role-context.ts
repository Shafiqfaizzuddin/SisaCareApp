import { createContext } from 'react'
import type { UserProfile, UserRole } from '../../types'

export interface RoleContextValue {
  role: UserRole
  user: UserProfile | null
  signInAs: (role: Exclude<UserRole, 'guest'>) => void
  signOut: () => void
  rewardMember: (points: number, validReport?: boolean) => void
}

export const RoleContext = createContext<RoleContextValue | null>(null)
