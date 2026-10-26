import { supabaseClient } from '../../lib/supabase'
import type { UserProfile } from '../../types'

export async function authFailureMessage(response: Response, fallback: string): Promise<string> {
  const body: unknown = await response.json().catch(() => null)
  if (body && typeof body === 'object' && 'detail' in body
    && typeof body.detail === 'string' && body.detail.trim()) return body.detail
  return fallback
}

export async function createBrowserSession(notify = true): Promise<void> {
  const { data } = await supabaseClient!.auth.getSession()
  if (!data.session?.access_token) throw new Error('Sign in again to start a browser session.')
  const response = await fetch('/api/auth/session', { method: 'POST', credentials: 'same-origin',
    headers: { Authorization: `Bearer ${data.session.access_token}` } })
  if (!response.ok) throw new Error(await authFailureMessage(response, 'The browser session could not be started.'))
  if (notify) window.dispatchEvent(new Event('sisacare:session-created'))
}

export async function loadBrowserSession(): Promise<UserProfile | null> {
  const response = await fetch('/api/auth/session', { credentials: 'same-origin', cache: 'no-store' })
  if (!response.ok) return null
  const value: unknown = await response.json()
  if (!value || typeof value !== 'object' || !('user_id' in value) || typeof value.user_id !== 'string'
    || !('role' in value) || (value.role !== 'admin' && value.role !== 'user')
    || !('email' in value) || typeof value.email !== 'string'
    || !('display_name' in value) || typeof value.display_name !== 'string') return null
  return { id: value.user_id, role: value.role, email: value.email, name: value.display_name,
    points: 0, title: value.role === 'admin' ? 'Administrator' : 'Community Member', validReports: 0 }
}

export async function revokeBrowserSession(): Promise<void> {
  const response = await fetch('/api/auth/session', { method: 'DELETE', credentials: 'same-origin' })
  if (!response.ok) throw new Error('The server session could not be revoked. Please try signing out again.')
}
