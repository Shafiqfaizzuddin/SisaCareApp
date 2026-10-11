import { beforeEach, describe, expect, it, vi } from 'vitest'

const { signInWithIdToken, signOut, linkIdentity, authenticatedFetch } = vi.hoisted(() => ({
  signInWithIdToken: vi.fn(), signOut: vi.fn(), linkIdentity: vi.fn(), authenticatedFetch: vi.fn(),
}))

vi.mock('../../lib/supabase', () => ({
  supabaseClient: { auth: { signInWithIdToken, signOut, linkIdentity } },
}))
vi.mock('./authenticated-fetch', () => ({ authenticatedFetch }))

import { linkGoogleIdentity, signInWithGoogle } from './google'

describe('Google account flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'approved' }) }))
    signInWithIdToken.mockResolvedValue({ error: null })
    linkIdentity.mockResolvedValue({ error: null })
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

  it('does not sign in after a server domain rejection', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: 'Use a verified UiTM Google account.' }) }))
    await expect(signInWithGoogle('invalid-domain-token')).rejects.toThrow('Use a verified UiTM Google account.')
    expect(signInWithIdToken).not.toHaveBeenCalled()
  })

  it('signs out if session completion fails', async () => {
    authenticatedFetch.mockResolvedValue({ ok: false })
    await expect(signInWithGoogle('google-id-token')).rejects.toThrow()
    expect(signOut).toHaveBeenCalled()
  })

  it('links only after a signed-in server verification', async () => {
    await linkGoogleIdentity('google-id-token')
    expect(linkIdentity).toHaveBeenCalledWith({ provider: 'google', token: 'google-id-token' })
  })
})
