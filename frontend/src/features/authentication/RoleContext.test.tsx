// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useState } from 'react'

const { getSession, onAuthStateChange, signInWithPassword, signUp, signOut, loadBrowserSession, fetchMemberDashboard } = vi.hoisted(() => ({
  getSession: vi.fn(), onAuthStateChange: vi.fn(), signInWithPassword: vi.fn(), signUp: vi.fn(), signOut: vi.fn(), loadBrowserSession: vi.fn(), fetchMemberDashboard: vi.fn(),
}))
vi.mock('./browser-session', () => ({ createBrowserSession: vi.fn().mockResolvedValue(undefined),
  loadBrowserSession, revokeBrowserSession: vi.fn().mockResolvedValue(undefined) }))
vi.mock('../../lib/supabase', () => ({
  supabaseClient: { auth: { getSession, onAuthStateChange, signInWithPassword, signUp, signOut } },
}))
vi.mock('../members/member-dashboard-api', () => ({ fetchMemberDashboard }))

import { RoleProvider } from './RoleContext'
import { useRole } from './useRole'

function Probe() {
  const { role, signIn, signOut: logout } = useRole()
  return <><span data-testid="role">{role}</span>
    <button onClick={() => void signIn('student@example.com', 'password', 'user')}>Login</button>
    <button onClick={() => void logout()}>Logout</button>
  </>
}

function VerificationProbe() {
  const { signIn, signUp: register } = useRole()
  const [message, setMessage] = useState('')
  return <><button onClick={() => void signIn('resident@gmail.com', 'password123', 'user')
    .catch((error: Error) => setMessage(error.message))}>Login unconfirmed</button>
    <button onClick={() => void register('Resident', 'resident@gmail.com', 'password123')
      .then((result) => setMessage(result.requiresEmailConfirmation ? 'Check email' : 'Signed in'))}>Register</button>
    <span data-testid="verification-message">{message}</span></>
}

beforeEach(() => {
  vi.clearAllMocks()
  getSession.mockResolvedValue({ data: { session: null } })
  onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
  signOut.mockResolvedValue({ error: null })
  loadBrowserSession.mockResolvedValue(null)
  fetchMemberDashboard.mockResolvedValue({ points: 0, validReports: 0, reports: [] })
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks() })

it('preserves password login and clears the participant on logout', async () => {
  signInWithPassword.mockResolvedValue({ data: { user: {
    id: 'student-1', email: 'student@example.com', email_confirmed_at: '2026-10-11T00:00:00Z',
    app_metadata: {}, user_metadata: { full_name: 'Student' },
  } }, error: null })
  render(<RoleProvider><Probe /></RoleProvider>)
  fireEvent.click(screen.getByText('Login'))
  await waitFor(() => expect(screen.getByTestId('role').textContent).toBe('user'))
  fireEvent.click(screen.getByText('Logout'))
  await waitFor(() => expect(screen.getByTestId('role').textContent).toBe('guest'))
  expect(signOut).toHaveBeenCalledOnce()
})

it('explains unconfirmed password sign-in so the user can request a new email', async () => {
  signInWithPassword.mockResolvedValue({ data: { user: null }, error: { code: 'email_not_confirmed' } })
  render(<RoleProvider><VerificationProbe /></RoleProvider>)
  fireEvent.click(screen.getByText('Login unconfirmed'))
  await waitFor(() => expect(screen.getByTestId('verification-message').textContent).toContain('Confirm your email'))
})

it('requests email verification for a first-time password registration', async () => {
  signUp.mockResolvedValue({ data: { user: { id: 'new-user', email_confirmed_at: null }, session: null }, error: null })
  render(<RoleProvider><VerificationProbe /></RoleProvider>)
  fireEvent.click(screen.getByText('Register'))
  await waitFor(() => expect(screen.getByTestId('verification-message').textContent).toBe('Check email'))
  expect(signUp).toHaveBeenCalledWith({ email: 'resident@gmail.com', password: 'password123',
    options: { data: { full_name: 'Resident' }, emailRedirectTo: `${window.location.origin}/login` } })
})

it('refreshes the idle session only while the signed-in user is active', async () => {
  vi.useFakeTimers()
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  loadBrowserSession.mockResolvedValue({ id: 'student-1', email: 'student@example.com', role: 'user', name: 'Student', points: 0, title: 'Community Member', validReports: 0 })
  render(<RoleProvider><Probe /></RoleProvider>)
  await act(async () => { await Promise.resolve() })
  expect(screen.getByTestId('role').textContent).toBe('user')
  const initialCalls = loadBrowserSession.mock.calls.length
  await act(async () => { await vi.advanceTimersByTimeAsync(4 * 60 * 1000) })
  fireEvent.keyDown(window, { key: 'a' })
  await act(async () => { await vi.advanceTimersByTimeAsync(60 * 1000) })
  expect(loadBrowserSession).toHaveBeenCalledTimes(initialCalls + 1)
  await act(async () => { await vi.advanceTimersByTimeAsync(5 * 60 * 1000) })
  expect(loadBrowserSession).toHaveBeenCalledTimes(initialCalls + 1)
})
