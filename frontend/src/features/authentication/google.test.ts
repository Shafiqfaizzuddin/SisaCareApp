// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { signInWithIdToken, signOut, linkIdentity, refreshSession, authenticatedFetch, createBrowserSession, revokeBrowserSession } = vi.hoisted(() => ({
  signInWithIdToken: vi.fn(), signOut: vi.fn(), linkIdentity: vi.fn(), refreshSession: vi.fn(), authenticatedFetch: vi.fn(), createBrowserSession: vi.fn(), revokeBrowserSession: vi.fn(),
}))

vi.mock('../../lib/supabase', () => ({
  supabaseClient: { auth: { signInWithIdToken, signOut, linkIdentity, refreshSession } },
}))
vi.mock('./authenticated-fetch', () => ({ authenticatedFetch }))
vi.mock('./browser-session', async (importOriginal) => ({
  ...await importOriginal<typeof import('./browser-session')>(), createBrowserSession, revokeBrowserSession,
}))

import { linkGoogleIdentity, loadGoogleIdentity, signInWithGoogle } from './google'

describe('Google account flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'approved' }) }))
    signInWithIdToken.mockResolvedValue({ error: null })
    linkIdentity.mockResolvedValue({ error: null })
    refreshSession.mockResolvedValue({ error: null })
    createBrowserSession.mockResolvedValue(undefined)
    revokeBrowserSession.mockResolvedValue(undefined)
    authenticatedFetch.mockResolvedValue({ ok: true })
  })

  it('checks Google with the server before asking Supabase for a session', async () => {
    await signInWithGoogle('google-id-token')
    expect(fetch).toHaveBeenCalledWith('/api/identity/google/preflight', expect.any(Object))
    expect(signInWithIdToken).toHaveBeenCalledWith({ provider: 'google', token: 'google-id-token' })
    expect(authenticatedFetch).toHaveBeenCalledWith('/api/identity/google/complete', expect.any(Object))
  })

  it('signs the same Google user in again after logout without registration', async () => {
    await signInWithGoogle('google-id-token')
    await signOut()
    await signInWithGoogle('google-id-token')
    expect(signInWithIdToken).toHaveBeenCalledTimes(2)
    expect(authenticatedFetch).toHaveBeenCalledTimes(2)
  })

  it('keeps genuine password-account collisions out of Supabase Google sign-in', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({
      detail: 'An account already uses this email. Sign in to that account and connect Google.',
    }) }))
    await expect(signInWithGoogle('google-id-token')).rejects.toThrow('An account already uses this email.')
    expect(signInWithIdToken).not.toHaveBeenCalled()
  })

  it('does not sign in after an unverified Google credential', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: 'Google email is not verified.' }) }))
    await expect(signInWithGoogle('unverified-token')).rejects.toThrow('Google email is not verified.')
    expect(signInWithIdToken).not.toHaveBeenCalled()
  })

  it('signs out if session completion fails', async () => {
    authenticatedFetch.mockResolvedValue({ ok: false })
    await expect(signInWithGoogle('google-id-token')).rejects.toThrow()
    expect(signOut).toHaveBeenCalled()
  })

  it('shows the server reason when the Google session cannot be completed', async () => {
    authenticatedFetch.mockResolvedValue({ ok: false, json: async () => ({ detail: 'Google email is not verified.' }) })
    await expect(signInWithGoogle('google-id-token')).rejects.toThrow('Google email is not verified.')
    expect(signOut).toHaveBeenCalled()
  })

  it('links only after a signed-in server verification', async () => {
    await linkGoogleIdentity('google-id-token')
    expect(linkIdentity).toHaveBeenCalledWith({ provider: 'google', token: 'google-id-token' })
  })
})

describe('Google Identity Services loading', () => {
  afterEach(() => {
    document.querySelectorAll('script[src="https://accounts.google.com/gsi/client"]').forEach((script) => script.remove())
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('retries a failed script load instead of keeping a rejected promise', async () => {
    vi.stubGlobal('google', undefined)
    const scripts: HTMLScriptElement[] = []
    vi.spyOn(document.head, 'appendChild').mockImplementation((node) => {
      scripts.push(node as HTMLScriptElement)
      return node
    })
    const first = loadGoogleIdentity()
    const failedScript = scripts[0]
    expect(failedScript).toBeTruthy()
    failedScript!.dispatchEvent(new Event('error'))
    await expect(first).rejects.toThrow('Google sign-in is unavailable.')

    const second = loadGoogleIdentity()
    expect(second).not.toBe(first)
    const nextScript = scripts[1]
    expect(nextScript).toBeTruthy()
    vi.stubGlobal('google', { accounts: { id: { renderButton: vi.fn() } } })
    nextScript!.dispatchEvent(new Event('load'))
    await expect(second).resolves.toBeUndefined()
  })
})
