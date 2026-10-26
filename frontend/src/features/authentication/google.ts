import { supabaseClient } from '../../lib/supabase'
import { authenticatedFetch } from './authenticated-fetch'
import { authFailureMessage, createBrowserSession, revokeBrowserSession } from './browser-session'

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (options: { client_id: string; callback: (response: { credential: string }) => void; auto_select?: boolean }) => void
          disableAutoSelect?: () => void
          renderButton: (element: HTMLElement, options: { theme: string; size: string; text: string; width?: number }) => void
        }
      }
    }
  }
}

export const googleClientId = (import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined)?.trim() ?? ''

let scriptPromise: Promise<void> | null = null
const GOOGLE_SCRIPT_TIMEOUT_MS = 10000
export function loadGoogleIdentity(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve()
  if (!scriptPromise) {
    const pending = new Promise<void>((resolve, reject) => {
      const script = document.createElement('script')
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.defer = true
      const timeout = window.setTimeout(() => fail(), GOOGLE_SCRIPT_TIMEOUT_MS)
      const fail = () => {
        window.clearTimeout(timeout)
        script.remove()
        reject(new Error('Google sign-in is unavailable.'))
      }
      script.onload = () => {
        window.clearTimeout(timeout)
        if (window.google?.accounts?.id) resolve()
        else fail()
      }
      script.onerror = fail
      document.head.appendChild(script)
    }).catch((error: unknown) => {
      scriptPromise = null
      throw error
    })
    scriptPromise = pending
  }
  return scriptPromise
}

async function verifyResponse(path: string, credential: string): Promise<void> {
  const response = await fetch(`/api/identity/google/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_token: credential }),
  })
  const value: unknown = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = value && typeof value === 'object' && 'detail' in value ? value.detail : null
    throw new Error(typeof detail === 'string' ? detail : 'Google verification failed.')
  }
}

export async function signInWithGoogle(credential: string): Promise<void> {
  if (!supabaseClient) throw new Error('Authentication is not configured.')
  await verifyResponse('preflight', credential)
  const { error } = await supabaseClient.auth.signInWithIdToken({ provider: 'google', token: credential })
  if (error) throw new Error(error.message)
  try {
    await createBrowserSession(false)
    const response = await authenticatedFetch('/api/identity/google/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_token: credential }),
    })
    if (!response.ok) throw new Error(await authFailureMessage(response, 'Google session verification failed.'))
    window.dispatchEvent(new Event('sisacare:session-created'))
  } catch (error) {
    await revokeBrowserSession().catch(() => undefined)
    await supabaseClient.auth.signOut()
    throw error
  }
}

export async function linkGoogleIdentity(credential: string): Promise<void> {
  if (!supabaseClient) throw new Error('Authentication is not configured.')
  const verified = await authenticatedFetch('/api/identity/google/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_token: credential }),
  })
  if (!verified.ok) throw new Error(await authFailureMessage(verified, 'Use a verified Google account.'))
  const { error } = await supabaseClient.auth.linkIdentity({ provider: 'google', token: credential })
  if (error) throw new Error(error.message)
  await supabaseClient.auth.refreshSession()
  await createBrowserSession()
  const response = await authenticatedFetch('/api/identity/google/complete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_token: credential }),
  })
  if (!response.ok) throw new Error(await authFailureMessage(response, 'Google identity was linked, but verification could not be saved.'))
}
