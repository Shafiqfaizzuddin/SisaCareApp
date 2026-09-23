import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { supabaseClient } from '../../lib/supabase'
import type { UserProfile } from '../../types'
import { RoleContext, type RoleContextValue } from './role-context'
import { AuthenticationError, profileFromAuthUser } from './session'

export function RoleProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [isAuthLoading, setIsAuthLoading] = useState(true)
  const appliedRewards = useRef(new Set<string>())

  useEffect(() => {
    if (!supabaseClient) {
      setIsAuthLoading(false)
      return
    }

    let active = true
    void supabaseClient.auth.getSession().then(({ data }) => {
      if (!active) return
      setUser(data.session?.user ? profileFromAuthUser(data.session.user) : null)
      setIsAuthLoading(false)
    })
    const { data } = supabaseClient.auth.onAuthStateChange((_event, session) => {
      if (!active) return
      setUser(session?.user ? profileFromAuthUser(session.user) : null)
      setIsAuthLoading(false)
    })

    return () => {
      active = false
      data.subscription.unsubscribe()
    }
  }, [])

  const signIn = useCallback(
    async (
      email: string,
      password: string,
      expectedRole: 'user' | 'admin',
    ) => {
      if (!supabaseClient) {
        throw new AuthenticationError(
          'Authentication is not configured. Add the Supabase URL and publishable key.',
        )
      }

      const { data, error } = await supabaseClient.auth.signInWithPassword({
        email: email.trim(),
        password,
      })
      if (error || !data.user) {
        throw new AuthenticationError('Email or password is incorrect.')
      }

      const profile = profileFromAuthUser(data.user)
      if (profile.role !== expectedRole) {
        await supabaseClient.auth.signOut()
        throw new AuthenticationError(
          expectedRole === 'admin'
            ? 'This account does not have administrator access.'
            : 'Administrator accounts must use the administrator sign-in page.',
        )
      }
      setUser(profile)
    },
    [],
  )

  const signOut = useCallback(async () => {
    if (supabaseClient) {
      await supabaseClient.auth.signOut()
    }
    setUser(null)
  }, [])

  const signUp = useCallback(
    async (fullName: string, email: string, password: string) => {
      if (!supabaseClient) {
        throw new AuthenticationError(
          'Authentication is not configured. Add the Supabase URL and publishable key.',
        )
      }

      const { data, error } = await supabaseClient.auth.signUp({
        email: email.trim(),
        password,
        options: {
          data: { full_name: fullName.trim() },
          emailRedirectTo: `${window.location.origin}/login`,
        },
      })
      if (error || !data.user) {
        throw new AuthenticationError(
          error?.message ?? 'The account could not be created. Please try again.',
        )
      }
      if (data.session) {
        setUser(profileFromAuthUser(data.user))
      }
      return { requiresEmailConfirmation: data.session === null }
    },
    [],
  )

  const value = useMemo<RoleContextValue>(() => {
    const role = user?.role ?? 'guest'

    return {
      role,
      user,
      isAuthLoading,
      signIn,
      signUp,
      signOut,
      rewardMember: (rewardKey, points, validReport = false) => {
        if (appliedRewards.current.has(rewardKey)) {
          return false
        }
        appliedRewards.current.add(rewardKey)
        setUser((current) =>
          current?.role === 'user'
            ? {
                ...current,
                points: current.points + points,
                validReports:
                  (current.validReports ?? 0) + (validReport ? 1 : 0),
              }
            : current,
        )
        return true
      },
    }
  }, [isAuthLoading, signIn, signOut, signUp, user])

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>
}
