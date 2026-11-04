// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { EmailDeliveryPanel } from './EmailDeliveryPanel'

const mocked = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock('../../features/authentication/authenticated-fetch', () => ({ authenticatedFetch: mocked.fetch }))
afterEach(() => { cleanup(); mocked.fetch.mockReset() })

it('shows masked failed delivery and requeues it through the admin API', async () => {
  const listing = { delivery_configured: { admin: true, citizen: true }, events: [{
    outbox_event_key: 'r1:resolved:e1', reference: 'SCA-1', event_type: 'resolved',
    delivery_status: 'failed', attempts: 5, last_error: 'OSError', next_attempt_at: null,
    recipient_hint: 'c***@example.com',
  }] }
  mocked.fetch.mockImplementation(async (_url: string, options?: RequestInit) => options?.method === 'POST'
    ? { ok: true, json: async () => ({ delivery_status: 'queued' }) }
    : { ok: true, json: async () => listing })
  render(<EmailDeliveryPanel />)
  await waitFor(() => expect(screen.getByText('c***@example.com')).toBeTruthy())
  expect(screen.getByText('OSError')).toBeTruthy()
  await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(mocked.fetch).toHaveBeenCalledWith('/api/admin/notifications/email/r1%3Aresolved%3Ae1/retry', { method: 'POST' })
})
