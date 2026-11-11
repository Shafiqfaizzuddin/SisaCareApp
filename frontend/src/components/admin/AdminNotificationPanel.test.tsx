// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AdminNotificationPanel } from './AdminNotificationPanel'

const mocked = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock('../../features/authentication/authenticated-fetch', () => ({ authenticatedFetch: mocked.fetch }))
afterEach(() => { cleanup(); mocked.fetch.mockReset(); vi.unstubAllGlobals() })

it('shows admin channel states and retries only failed delivery', async () => {
  vi.stubGlobal('Option', function Option(text: string, value: string) {
    const option = document.createElement('option'); option.text = text; option.value = value; return option
  })
  const result = { delivery_configured: { email: true, telegram: true }, events: [
    { event_key: 'e1:telegram', reference: 'SCA-1', new_status: 'assigned', channel: 'telegram',
      delivery_status: 'failed', recipient_hint: 'Private admin channel', attempts: 5, last_error: 'TelegramDeliveryError' },
    { event_key: 'e2:email', reference: 'SCA-2', new_status: 'resolved', channel: 'email',
      delivery_status: 'sent', recipient_hint: 'a***@example.com', attempts: 1, last_error: null },
  ] }
  mocked.fetch.mockImplementation(async (_url: string, options?: RequestInit) => options?.method === 'POST'
    ? { ok: true, json: async () => ({ delivery_status: 'queued' }) }
    : { ok: true, json: async () => result })
  render(<AdminNotificationPanel />)
  await waitFor(() => expect(screen.getByText('Private admin channel')).toBeTruthy())
  expect(screen.getByText('TelegramDeliveryError')).toBeTruthy()
  const buttons = screen.getAllByRole('button', { name: 'Retry' }) as HTMLButtonElement[]
  expect(buttons.some(button => button.disabled)).toBe(true)
  await userEvent.click(buttons.find(button => !button.disabled)!)
  expect(mocked.fetch).toHaveBeenCalledWith('/api/admin/notifications/admin/e1%3Atelegram/retry', { method: 'POST' })
})
