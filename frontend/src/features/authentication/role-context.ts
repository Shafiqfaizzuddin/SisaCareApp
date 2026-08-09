import { createContext } from 'react'
import type { UserProfile, UserRole } from '../../types'

export interface RoleContextValue {
  role: UserRole
  user: UserProfile | null
  authLoading: boolean
  signIn: (
    email: string,
    password: string,
  ) => Promise<{ error: string | null; role?: Exclude<UserRole, 'guest'> }>
  signUp: (
    name: string,
    email: string,
    password: string,
  ) => Promise<{ error: string | null; requiresConfirmation: boolean }>
  signOut: () => Promise<void>
  refreshProfile: () => Promise<void>
}

export const RoleContext = createContext<RoleContextValue | null>(null)
