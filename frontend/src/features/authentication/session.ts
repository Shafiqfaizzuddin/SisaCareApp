import type { User } from '@supabase/supabase-js'
import type { UserProfile } from '../../types'

export interface AdminCredentials {
  email: string
  password: string
}

export const emptyAdminCredentials: AdminCredentials = {
  email: '',
  password: '',
}

export class AuthenticationError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AuthenticationError'
  }
}

function metadataString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function fallbackName(email: string): string {
  const localPart = email.split('@')[0] || 'Member'
  return localPart
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function profileFromAuthUser(user: User): UserProfile {
  const email = user.email ?? ''
  const isAdmin = user.app_metadata.role === 'admin'
  const metadataName =
    metadataString(user.user_metadata.full_name) ??
    metadataString(user.user_metadata.name)

  return {
    id: user.id,
    name: metadataName ?? fallbackName(email),
    email,
    role: isAdmin ? 'admin' : 'user',
    points: 0,
    title: isAdmin
      ? metadataString(user.app_metadata.title) ?? 'Municipal Administrator'
      : 'Community Member',
    rank: undefined,
    validReports: 0,
  }
}
