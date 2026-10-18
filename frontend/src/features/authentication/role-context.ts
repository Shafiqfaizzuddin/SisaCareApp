import { createContext } from 'react'
import type { MemberReportSummary, UserProfile, UserRole } from '../../types'

export interface SignUpResult {
  requiresEmailConfirmation: boolean
}

export interface RoleContextValue {
  role: UserRole
  user: UserProfile | null
  isAuthLoading: boolean
  signIn: (
    email: string,
    password: string,
    expectedRole: Exclude<UserRole, 'guest'>,
  ) => Promise<void>
  signUp: (
    fullName: string,
    email: string,
    password: string,
  ) => Promise<SignUpResult>
  signOut: () => Promise<void>
  memberReports: MemberReportSummary[]
  isMemberDataLoading: boolean
  memberDataError: string
  refreshMemberData: () => void
}

export const RoleContext = createContext<RoleContextValue | null>(null)
