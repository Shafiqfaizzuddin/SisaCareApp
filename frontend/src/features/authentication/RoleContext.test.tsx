// @vitest-environment happy-dom
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'

const { getSession, onAuthStateChange, signInWithPassword, signOut, fetchMemberDashboard } = vi.hoisted(() => ({
  getSession: vi.fn(), onAuthStateChange: vi.fn(), signInWithPassword: vi.fn(), signOut: vi.fn(), fetchMemberDashboard: vi.fn(),
}))
vi.mock('../../lib/supabase', () => ({
  supabaseClient: { auth: { getSession, onAuthStateChange, signInWithPassword, signOut } },
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

beforeEach(() => {
  vi.clearAllMocks()
  getSession.mockResolvedValue({ data: { session: null } })
  onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
  signOut.mockResolvedValue({ error: null })
  fetchMemberDashboard.mockResolvedValue({ points: 0, validReports: 0, reports: [] })
})

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
