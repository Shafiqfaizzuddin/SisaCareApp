// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

vi.mock('../features/authentication/useRole', () => ({ useRole: () => ({ user: { id: 'member-1', rank: 1 } }) }))
import { LeaderboardPage } from './LeaderboardPage'

beforeEach(() => {
  vi.stubGlobal('Option', function Option(text: string, value: string) {
    const option = document.createElement('option'); option.text = text; option.value = value; return option
  })
  vi.stubGlobal('fetch', vi.fn((input: string) => Promise.resolve({ ok: true, json: async () => ({
    total: 52,
    entries: input.includes('offset=50')
      ? [{ id: 'member-51', name: 'Later Member', points: 20, valid_reports: 1, rank: 51 }]
      : [{ id: 'member-1', name: 'First Member', points: 100, valid_reports: 5, rank: 1 }],
  }) })))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('shows server-paged rankings without a second DataTables pager', async () => {
  render(<LeaderboardPage />)
  expect(await screen.findByText('First Member')).toBeTruthy()
  expect(await screen.findByText('You')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Next page' })).toBeNull()
  await userEvent.click(screen.getByRole('button', { name: 'Next' }))
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/members/leaderboard?limit=50&offset=50', expect.anything()))
  expect(await screen.findByText('Later Member')).toBeTruthy()
})
