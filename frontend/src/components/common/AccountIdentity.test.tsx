// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const { authenticatedFetch, getUser } = vi.hoisted(() => ({ authenticatedFetch: vi.fn(), getUser: vi.fn() }))
vi.mock('../../features/authentication/authenticated-fetch', () => ({ authenticatedFetch }))
vi.mock('../../features/authentication/google', () => ({ linkGoogleIdentity: vi.fn() }))
vi.mock('../../lib/supabase', () => ({ supabaseClient: { auth: { getUser } } }))
vi.mock('./GoogleIdentityButton', () => ({ GoogleIdentityButton: () => <button type="button">Connect Google</button> }))

import { AccountIdentity } from './AccountIdentity'

const identity = {
  google_sub: 'google-1', claimed_affiliation: 'student', matric_number: '2025516823',
  matric_source: 'verified_email', matric_status: 'not_submitted', matric_submitted_at: null,
  matric_rejection_reason: null, e_merit_identity_eligible: false, e_merit_available_points: 0,
}
const ok = (value: object) => ({ ok: true, json: async () => value })

beforeEach(() => {
  vi.clearAllMocks()
  getUser.mockResolvedValue({ data: { user: { user_metadata: { claimed_affiliation: 'student' } } } })
})
afterEach(() => cleanup())

it('shows the extracted suggestion and records a correction as self-reported after submission', async () => {
  const user = userEvent.setup()
  authenticatedFetch.mockResolvedValueOnce(ok(identity))
    .mockResolvedValueOnce(ok({ ...identity, matric_number: 'corrected', matric_source: 'self_reported', matric_status: 'pending', matric_submitted_at: '2026-10-11T00:00:00Z' }))
  render(<AccountIdentity />)
  const input = await screen.findByLabelText('Matric number') as HTMLInputElement
  expect(input.value).toBe('2025516823')
  expect(screen.getByText(/Suggested from your verified student email/)).toBeTruthy()
  await user.clear(input)
  await user.type(input, 'corrected')
  await user.click(screen.getByRole('button', { name: 'Submit matric for verification' }))
  await waitFor(() => expect(screen.getByText(/Status:/).textContent).toContain('Pending'))
  const request = authenticatedFetch.mock.calls[1]
  expect(request[0]).toBe('/api/identity/me/matric')
  expect(JSON.parse(request[1].body)).toEqual({ matric_number: 'corrected' })
})

it('shows a rejection reason and lets the student resubmit', async () => {
  const user = userEvent.setup()
  authenticatedFetch.mockResolvedValueOnce(ok({ ...identity, matric_status: 'rejected', matric_rejection_reason: 'Record did not match' }))
    .mockResolvedValueOnce(ok({ ...identity, matric_status: 'pending', matric_rejection_reason: null }))
  render(<AccountIdentity />)
  expect(await screen.findByText('Reason: Record did not match')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: 'Correct and resubmit' }))
  await waitFor(() => expect(screen.getByText(/Status:/).textContent).toContain('Pending'))
})
