// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const auth = vi.hoisted(() => ({ getUser: vi.fn(), getSession: vi.fn(), updateUser: vi.fn(), signOut: vi.fn() }))
vi.mock('../lib/supabase', () => ({ supabaseClient: { auth } }))
vi.mock('../features/theme/useTheme', () => ({ useTheme: () => ({ theme: 'light', toggleTheme: () => {} }) }))
import { StaffAcceptInvitePage } from './StaffAcceptInvitePage'

beforeEach(() => {
  auth.getUser.mockReset().mockResolvedValue({ data: { user: { id: 'worker-id', email: 'worker@example.com' } }, error: null })
  auth.getSession.mockReset().mockResolvedValue({ data: { session: { access_token: 'invite-token' } }, error: null })
  auth.updateUser.mockReset().mockResolvedValue({ error: null })
  auth.signOut.mockReset().mockResolvedValue({ error: null })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ user_id: 'worker-id', email: 'worker@example.com' }) }))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('verifies the invite session, sets a password, and directs staff to sign in', async () => {
  render(<MemoryRouter><StaffAcceptInvitePage /></MemoryRouter>)
  await screen.findByText('Account: worker@example.com')
  expect(fetch).toHaveBeenCalledWith('/api/collection/staff/invite/identity', { headers: { Authorization: 'Bearer invite-token' } })
  await userEvent.type(screen.getByLabelText('New password'), 'strong-pass-123')
  await userEvent.type(screen.getByLabelText('Confirm password'), 'strong-pass-123')
  expect(screen.getByText('Passwords match.')).toBeTruthy()
  await userEvent.click(screen.getByRole('button', { name: 'Set password' }))
  await waitFor(() => expect(auth.updateUser).toHaveBeenCalledWith({ password: 'strong-pass-123' }))
  expect(auth.signOut).toHaveBeenCalledOnce()
  expect((await screen.findByRole('status')).textContent).toContain('Password saved')
  expect(screen.getByRole('link', { name: 'Sign in to the staff dashboard' }).getAttribute('href')).toBe('/staff/login')
})

it('does not offer password setup when the invitation session is invalid', async () => {
  auth.getUser.mockResolvedValue({ data: { user: null }, error: new Error('expired') })
  render(<MemoryRouter><StaffAcceptInvitePage /></MemoryRouter>)
  expect((await screen.findByRole('alert')).textContent).toContain('invalid or expired')
  expect(screen.queryByRole('button', { name: 'Set password' })).toBeNull()
  expect(auth.updateUser).not.toHaveBeenCalled()
})

it('rejects an existing session without a staff grant', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 403 }))
  render(<MemoryRouter><StaffAcceptInvitePage /></MemoryRouter>)
  expect((await screen.findByRole('alert')).textContent).toContain('not linked to an active staff')
  expect(screen.queryByRole('button', { name: 'Set password' })).toBeNull()
})

it('requires matching passwords and supports visibility toggle', async () => {
  render(<MemoryRouter><StaffAcceptInvitePage /></MemoryRouter>)
  await screen.findByText('Account: worker@example.com')
  await userEvent.type(screen.getByLabelText('New password'), 'strong-pass-123')
  await userEvent.type(screen.getByLabelText('Confirm password'), 'different-pass-123')
  expect(screen.getByText('Passwords do not match yet.')).toBeTruthy()
  expect((screen.getByRole('button', { name: 'Set password' }) as HTMLButtonElement).disabled).toBe(true)
  await userEvent.click(screen.getByLabelText('Show passwords'))
  expect((screen.getByLabelText('New password') as HTMLInputElement).type).toBe('text')
  expect(auth.updateUser).not.toHaveBeenCalled()
})
