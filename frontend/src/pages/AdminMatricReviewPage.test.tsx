// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const { authenticatedFetch } = vi.hoisted(() => ({ authenticatedFetch: vi.fn() }))
vi.mock('../features/authentication/authenticated-fetch', () => ({ authenticatedFetch }))
import { AdminMatricReviewPage } from './AdminMatricReviewPage'

beforeEach(() => vi.clearAllMocks())
afterEach(() => cleanup())

it('shows the pending queue and records a documented manual rejection', async () => {
  const user = userEvent.setup()
  authenticatedFetch.mockResolvedValueOnce({ ok: true, json: async () => [{
    user_id: 'student-1', matric_number: '2025516823', matric_source: 'self_reported',
    matric_submitted_at: '2026-10-11T00:00:00Z', matric_submitted_email: 'student@student.uitm.edu.my',
  }] }).mockResolvedValueOnce({ ok: true, json: async () => ({ decision: 'rejected' }) })
  render(<AdminMatricReviewPage />)
  expect(await screen.findByText('Matric: 2025516823')).toBeTruthy()
  await user.selectOptions(screen.getByLabelText('Decision'), 'rejected')
  await user.type(screen.getByLabelText('Record or procedure checked'), 'Agreed register checked')
  await user.type(screen.getByLabelText('Rejection reason shown to student'), 'Record did not match')
  await user.click(screen.getByRole('checkbox'))
  await user.click(screen.getByRole('button', { name: 'Save review' }))
  await waitFor(() => expect(screen.getByText('No matric submissions are pending.')).toBeTruthy())
  const request = authenticatedFetch.mock.calls[1]
  expect(request[0]).toBe('/api/identity/admin/matric/student-1/review')
  expect(JSON.parse(request[1].body)).toMatchObject({
    decision: 'rejected', verification_method: 'prototype_manual', procedure_confirmed: true,
    rejection_reason: 'Record did not match',
  })
})
