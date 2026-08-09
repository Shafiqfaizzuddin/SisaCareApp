import type { User } from '@supabase/supabase-js'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { supabase } from '../../lib/supabase'
import type { UserProfile, UserRole } from '../../types'
import { RoleContext, type RoleContextValue } from './role-context'

interface ProfileRow {
  id: string
  name: string
  email: string
  role: 'user' | 'admin'
  points: number
  title: string
  valid_reports: number
}

function toUserProfile(profile: ProfileRow): UserProfile {
  return {
    id: profile.id,
    name: profile.name,
    email: profile.email,
    role: profile.role,
    points: profile.points,
    title: profile.title,
    validReports: profile.valid_reports,
  }
}

export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<UserRole>('guest')
  const [user, setUser] = useState<UserProfile | null>(null)
  const [authLoading, setAuthLoading] = useState(true)

  const clearSession = useCallback(() => {
    setRole('guest')
    setUser(null)
    setAuthLoading(false)
  }, [])

  const loadProfile = useCallback(async (authUser: User) => {
    const { data, error } = await supabase
      .from('profiles')
      .select('id, name, email, role, points, title, valid_reports')
      .eq('id', authUser.id)
      .single<ProfileRow>()

    if (error) throw error

    const profile = toUserProfile(data)

    if (profile.role === 'user') {
      const { data: rank } = await supabase
        .from('leaderboard_view')
        .select('points_rank')
        .eq('user_id', profile.id)
        .maybeSingle()
      profile.rank = rank?.points_rank ? Number(rank.points_rank) : undefined
    }
    setUser(profile)
    setRole(profile.role)
    setAuthLoading(false)
    return profile
  }, [])

  useEffect(() => {
    let active = true
    const timers = new Set<number>()

    async function restoreSession() {
      const { data, error } = await supabase.auth.getUser()

      if (!active) return
      if (error || !data.user) {
        clearSession()
        return
      }

      try {
        await loadProfile(data.user)
      } catch {
        if (active) clearSession()
      }
    }

    void restoreSession()

    const { data: authListener } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        if (!session?.user) {
          clearSession()
          return
        }

        const timer = window.setTimeout(() => {
          timers.delete(timer)
          if (!active) return
          void loadProfile(session.user).catch(() => {
            if (active) clearSession()
          })
        }, 0)
        timers.add(timer)
      },
    )

    return () => {
      active = false
      timers.forEach((timer) => window.clearTimeout(timer))
      authListener.subscription.unsubscribe()
    }
  }, [clearSession, loadProfile])

  const value = useMemo<RoleContextValue>(
    () => ({
      role,
      user,
      authLoading,
      signIn: async (email, password) => {
        const { data, error } = await supabase.auth.signInWithPassword({
          email: email.trim(),
          password,
        })

        if (error || !data.user) {
          return { error: error?.message ?? 'Unable to sign in.' }
        }

        try {
          const profile = await loadProfile(data.user)
          return { error: null, role: profile.role }
        } catch {
          await supabase.auth.signOut()
          clearSession()
          return { error: 'Your account profile could not be loaded.' }
        }
      },
      signUp: async (name, email, password) => {
        const { data, error } = await supabase.auth.signUp({
          email: email.trim(),
          password,
          options: {
            data: { name: name.trim() },
            emailRedirectTo: `${window.location.origin}/login?confirmed=1`,
          },
        })

        if (error) {
          return { error: error.message, requiresConfirmation: false }
        }

        if (data.session && data.user) {
          try {
            await loadProfile(data.user)
          } catch {
            await supabase.auth.signOut()
            clearSession()
            return {
              error: 'Your account was created, but its profile could not be loaded.',
              requiresConfirmation: false,
            }
          }
        }

        return { error: null, requiresConfirmation: !data.session }
      },
      signOut: async () => {
        await supabase.auth.signOut()
        clearSession()
      },
      refreshProfile: async () => {
        const { data, error } = await supabase.auth.getUser()
        if (error || !data.user) {
          clearSession()
          return
        }
        await loadProfile(data.user)
      },
    }),
    [authLoading, clearSession, loadProfile, role, user],
  )

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>
}
