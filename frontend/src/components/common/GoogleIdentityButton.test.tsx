// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const { loadGoogleIdentity, initialize, renderButton } = vi.hoisted(() => ({
  loadGoogleIdentity: vi.fn(), initialize: vi.fn(), renderButton: vi.fn(),
}))
vi.mock('../../features/authentication/google', () => ({ googleClientId: 'test-web-client', loadGoogleIdentity }))

import { GoogleIdentityButton } from './GoogleIdentityButton'

beforeEach(() => {
  vi.clearAllMocks()
  loadGoogleIdentity.mockResolvedValue(undefined)
  renderButton.mockImplementation((element: HTMLElement) => {
    const button = document.createElement('button')
    button.textContent = 'Google widget'
    element.append(button)
  })
  vi.stubGlobal('google', { accounts: { id: { initialize, renderButton } } })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })

it('shows a visible loading control and then the Google widget', async () => {
  render(<GoogleIdentityButton onCredential={vi.fn()} onError={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Loading Google sign-in...' })).toBeTruthy()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Google widget' })).toBeTruthy())
})

it('offers retry after a script failure and renders the widget on retry', async () => {
  loadGoogleIdentity.mockRejectedValueOnce(new Error('network unavailable'))
  render(<GoogleIdentityButton onCredential={vi.fn()} onError={vi.fn()} />)
  const retry = await screen.findByRole('button', { name: 'Retry Google sign-in' })
  fireEvent.click(retry)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Google widget' })).toBeTruthy())
  expect(loadGoogleIdentity).toHaveBeenCalledTimes(2)
})

it('renders again when the login page remounts after session expiry', async () => {
  const first = render(<GoogleIdentityButton onCredential={vi.fn()} onError={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Google widget' })).toBeTruthy())
  first.unmount()
  render(<GoogleIdentityButton onCredential={vi.fn()} onError={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Google widget' })).toBeTruthy())
  expect(initialize).toHaveBeenCalledTimes(2)
})

it('offers retry if Google loads but does not insert a button', async () => {
  vi.useFakeTimers()
  renderButton.mockImplementation(() => undefined)
  render(<GoogleIdentityButton onCredential={vi.fn()} onError={vi.fn()} />)
  await act(async () => { await Promise.resolve() })
  await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
  expect(screen.getByRole('button', { name: 'Retry Google sign-in' })).toBeTruthy()
})
