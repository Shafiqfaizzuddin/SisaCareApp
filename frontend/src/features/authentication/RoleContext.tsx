import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { supabaseClient } from '../../lib/supabase'
import type { MemberReportSummary, UserProfile } from '../../types'
import {
  fetchMemberDashboard,
  MemberDashboardRequestError,
} from '../members/member-dashboard-api'
import { memberTitleForPoints } from './member-data'
import { RoleContext, type RoleContextValue } from './role-context'
import { AuthenticationError, profileFromAuthUser } from './session'

export function RoleProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [isAuthLoading, setIsAuthLoading] = useState(true)
  const [memberReports, setMemberReports] = useState<MemberReportSummary[]>([])
  const [isMemberDataLoading, setIsMemberDataLoading] = useState(false)
  const [memberDataError, setMemberDataError] = useState('')
  const [memberRefreshVersion, setMemberRefreshVersion] = useState(0)

  useEffect(() => {
    if (!supabaseClient) {
      setIsAuthLoading(false)
      return
    }

    let active = true
    void supabaseClient.auth.getSession().then(({ data }) => {
      if (!active) return
      const profile = data.session?.user
        ? profileFromAuthUser(data.session.user)
        : null
      setUser(profile)
      setIsAuthLoading(false)
    })
    const { data } = supabaseClient.auth.onAuthStateChange((_event, session) => {
      if (!active) return
      const profile = session?.user ? profileFromAuthUser(session.user) : null
      setUser((current) =>
        profile && current?.id === profile.id && current.role === 'user'
          ? {
              ...profile,
              points: current.points,
              title: current.title,
              rank: current.rank,
              validReports: current.validReports,
            }
          : profile,
      )
      setIsAuthLoading(false)
    })

    return () => {
      active = false
      data.subscription.unsubscribe()
    }
  }, [])

  useEffect(() => {
    if (user?.role !== 'user') {
      setMemberReports([])
      setMemberDataError('')
      setIsMemberDataLoading(false)
      return
    }

    const memberId = user.id
    const controller = new AbortController()
    setIsMemberDataLoading(true)
    setMemberDataError('')

    void fetchMemberDashboard(controller.signal)
      .then((dashboard) => {
        if (controller.signal.aborted) return
        setMemberReports(dashboard.reports)
        setUser((current) =>
          current?.id === memberId && current.role === 'user'
            ? {
                ...current,
                points: dashboard.points,
                validReports: dashboard.validReports,
                rank: dashboard.rank,
                title: memberTitleForPoints(dashboard.points),
              }
            : current,
        )
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setMemberDataError(
          error instanceof MemberDashboardRequestError
            ? error.message
            : 'The member dashboard could not be loaded.',
        )
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsMemberDataLoading(false)
        }
      })

    return () => controller.abort()
  }, [memberRefreshVersion, user?.id, user?.role])

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

  const refreshMemberData = useCallback(() => {
    setMemberRefreshVersion((version) => version + 1)
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
      memberReports,
      isMemberDataLoading,
      memberDataError,
      signIn,
      signUp,
      signOut,
      refreshMemberData,
    }
  }, [
    isAuthLoading,
    isMemberDataLoading,
    memberDataError,
    memberReports,
    refreshMemberData,
    signIn,
    signOut,
    signUp,
    user,
  ])

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>
}
