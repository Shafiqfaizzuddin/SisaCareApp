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
import { loadBrowserSession, createBrowserSession, revokeBrowserSession } from './browser-session'

const SESSION_HEARTBEAT_MS = 5 * 60 * 1000

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
    const client = supabaseClient

    let active = true
    void loadBrowserSession().then((profile) => {
      if (!active) return
      setUser(current => profile ?? current)
      setIsAuthLoading(false)
    }).catch(() => { if (active) setIsAuthLoading(false) })
    const { data } = client.auth.onAuthStateChange((event) => {
      if (!active) return
      if (event === 'SIGNED_OUT') { setUser(null); setMemberReports([]); setIsAuthLoading(false) }
    })
    const recheck = () => { void loadBrowserSession().then((profile) => {
      if (!active) return
      setUser(current => profile && current?.id === profile.id ? { ...profile, points: current.points,
        title: current.title, rank: current.rank, validReports: current.validReports } : profile)
      setIsAuthLoading(false)
    }).catch(() => { if (active) setUser(null) }) }
    window.addEventListener('focus', recheck)
    window.addEventListener('sisacare:session-created', recheck)
    const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('sisacare-auth')
    if (channel) channel.onmessage = (message: MessageEvent<string>) => {
      if (message.data === 'signed-out') { setUser(null); setMemberReports([]) }
    }
    const onVisible = () => { if (document.visibilityState === 'visible') recheck() }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      active = false
      data.subscription.unsubscribe()
      window.removeEventListener('focus', recheck)
      window.removeEventListener('sisacare:session-created', recheck)
      document.removeEventListener('visibilitychange', onVisible)
      channel?.close()
    }
  }, [])

  useEffect(() => {
    if (!user) return
    const signedInUserId = user.id
    let lastActivityAt = Date.now()
    let heartbeatInFlight = false
    const markActivity = () => { lastActivityAt = Date.now() }
    const heartbeat = () => {
      if (heartbeatInFlight || document.visibilityState !== 'visible'
        || Date.now() - lastActivityAt >= SESSION_HEARTBEAT_MS) return
      heartbeatInFlight = true
      void loadBrowserSession().then((profile) => {
        if (!profile || profile.id !== signedInUserId) {
          setUser((current) => current?.id === signedInUserId ? null : current)
          setMemberReports([])
        }
      }).catch(() => undefined).finally(() => { heartbeatInFlight = false })
    }
    window.addEventListener('pointerdown', markActivity)
    window.addEventListener('keydown', markActivity)
    window.addEventListener('scroll', markActivity, { passive: true })
    const interval = window.setInterval(heartbeat, SESSION_HEARTBEAT_MS)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('pointerdown', markActivity)
      window.removeEventListener('keydown', markActivity)
      window.removeEventListener('scroll', markActivity)
    }
  }, [user?.id])

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
        if (error instanceof MemberDashboardRequestError && error.message.includes('session has expired')) {
          setUser(null)
          setMemberReports([])
          return
        }
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
      if (error?.code === 'email_not_confirmed') {
        throw new AuthenticationError('Confirm your email before signing in. You can resend the confirmation email below.')
      }
      if (error || !data.user) {
        throw new AuthenticationError('Email or password is incorrect.')
      }
      if (!data.user.email_confirmed_at) {
        await supabaseClient.auth.signOut()
        throw new AuthenticationError('Confirm your email before signing in.')
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
      try { await createBrowserSession() } catch (error) {
        await supabaseClient.auth.signOut()
        throw new AuthenticationError(error instanceof Error ? error.message : 'Browser session could not be started.')
      }
      setUser(profile)
    },
    [],
  )

  const signOut = useCallback(async () => {
    await revokeBrowserSession()
    if (typeof BroadcastChannel !== 'undefined') {
      const channel = new BroadcastChannel('sisacare-auth')
      channel.postMessage('signed-out')
      channel.close()
    }
    window.google?.accounts.id.disableAutoSelect?.()
    try {
      if (supabaseClient) await supabaseClient.auth.signOut()
    } finally {
      setUser(null)
      setMemberReports([])
    }
  }, [])

  const refreshMemberData = useCallback(() => {
    setMemberRefreshVersion((version) => version + 1)
  }, [])

  const syncBrowserSession = useCallback(async () => {
    const profile = await loadBrowserSession()
    if (!profile) throw new AuthenticationError('The Google session could not be restored. Please try again.')
    setUser(profile)
    setIsAuthLoading(false)
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
      if (data.session && data.user.email_confirmed_at) {
        await createBrowserSession()
        setUser(profileFromAuthUser(data.user))
      } else if (data.session) {
        await supabaseClient.auth.signOut()
      }
      return { requiresEmailConfirmation: !data.user.email_confirmed_at }
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
      syncBrowserSession,
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
    syncBrowserSession,
    user,
  ])

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>
}
