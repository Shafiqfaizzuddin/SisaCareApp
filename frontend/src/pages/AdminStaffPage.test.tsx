// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AdminStaffPage } from './AdminStaffPage'

const api = vi.hoisted(() => ({ inviteStaff: vi.fn(), listStaff: vi.fn(), grantStaff: vi.fn(), revokeStaff: vi.fn(), resendStaffVerification: vi.fn() }))
vi.mock('../features/collection/collection-api', () => api)

beforeEach(() => {
  api.inviteStaff.mockReset().mockResolvedValue({ user_id: 'user-1', email: 'worker@example.com', role: 'driver', invitation_sent: true })
  api.listStaff.mockReset().mockResolvedValue([])
  api.grantStaff.mockReset()
  api.revokeStaff.mockReset()
  api.resendStaffVerification.mockReset().mockResolvedValue({ user_id: 'user-1', email: 'worker@example.com', verification_email_requested: true })
})
afterEach(cleanup)

it('lets an administrator create a driver account by invitation and shows its grant', async () => {
  api.listStaff.mockResolvedValueOnce([]).mockResolvedValueOnce([{
    user_id: 'user-1', role: 'driver', email: 'worker@example.com', display_name: 'New Worker',
    granted_at: '2026-11-09T00:00:00Z', invited_at: '2026-11-09T00:00:00Z', revoked_at: null,
    verification_status: 'unverified',
  }])
  render(<AdminStaffPage />)
  await userEvent.type(screen.getByRole('textbox', { name: 'Full name' }), 'New Worker')
  await userEvent.type(screen.getByRole('textbox', { name: 'Email address' }), 'worker@example.com')
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Role' }), 'driver')
  await userEvent.click(screen.getByRole('button', { name: 'Create account and send invite' }))
  await waitFor(() => expect(api.inviteStaff).toHaveBeenCalledWith('worker@example.com', 'New Worker', 'driver'))
  expect(await screen.findByText(/Invitation sent to worker@example.com/)).toBeTruthy()
  expect(screen.getByText('New Worker')).toBeTruthy()
  expect(screen.getByText('Driver · Active · Invited by email')).toBeTruthy()
})

it('resends only for an unverified account and disables verified accounts', async () => {
  api.listStaff.mockResolvedValue([
    { user_id: 'user-1', role: 'driver', email: 'worker@example.com', granted_at: '2026-11-09', revoked_at: null, verification_status: 'unverified' },
    { user_id: 'user-2', role: 'staff', email: 'verified@example.com', granted_at: '2026-11-09', revoked_at: null, verification_status: 'verified' },
  ])
  render(<AdminStaffPage />)
  await screen.findByText('worker@example.com')
  const buttons = screen.getAllByRole('button', { name: 'Resend verification email' }) as HTMLButtonElement[]
  expect(buttons[0].disabled).toBe(false)
  expect(buttons[1].disabled).toBe(true)
  await userEvent.click(buttons[0])
  await waitFor(() => expect(api.resendStaffVerification).toHaveBeenCalledWith('user-1'))
  expect((await screen.findByRole('status')).textContent).toContain('worker@example.com')
})

it('keeps resend disabled when verification cannot be checked or the grant is revoked', async () => {
  api.listStaff.mockResolvedValue([
    { user_id: 'user-1', role: 'staff', email: 'unknown@example.com', granted_at: '2026-11-09', revoked_at: null, verification_status: 'unknown' },
    { user_id: 'user-2', role: 'driver', email: 'revoked@example.com', granted_at: '2026-11-09', revoked_at: '2026-11-09', verification_status: 'unverified' },
  ])
  render(<AdminStaffPage />)
  await screen.findByText('unknown@example.com')
  const buttons = screen.getAllByRole('button', { name: 'Resend verification email' }) as HTMLButtonElement[]
  expect(buttons.every(button => button.disabled)).toBe(true)
  expect(api.resendStaffVerification).not.toHaveBeenCalled()
})

it('shows an invitation failure without claiming an account was created', async () => {
  api.inviteStaff.mockRejectedValue(new Error('Supabase could not send the staff invitation.'))
  render(<AdminStaffPage />)
  await userEvent.type(screen.getByRole('textbox', { name: 'Full name' }), 'Worker')
  await userEvent.type(screen.getByRole('textbox', { name: 'Email address' }), 'worker@example.com')
  await userEvent.click(screen.getByRole('button', { name: 'Create account and send invite' }))
  expect((await screen.findByRole('alert')).textContent).toContain('Supabase could not send the staff invitation.')
  expect(screen.queryByText(/Invitation sent to/)).toBeNull()
})
