// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AdminDashboardPage } from './AdminDashboardPage'

const mocks = vi.hoisted(() => ({ fetchPersistedReports: vi.fn() }))
vi.mock('../features/admin-reports/admin-reports-api', () => ({ fetchPersistedReports: mocks.fetchPersistedReports }))

beforeEach(() => mocks.fetchPersistedReports.mockReset().mockResolvedValue([{
  id: 'haz-1', reference: 'SCA-HAZ-1', category: 'Hazardous Waste', location: 'Campus Gate',
  submittedAt: '13 Oct 2026', status: 'submitted', confidence: null, description: 'Battery',
  reporter: 'Member', reporterRole: 'user', validationStatus: 'pending',
}]))
afterEach(cleanup)

it('keeps hazardous reports in the admin list and category filter', async () => {
  render(<MemoryRouter><AdminDashboardPage /></MemoryRouter>)
  await waitFor(() => expect(screen.getByText('SCA-HAZ-1')).toBeTruthy())
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Filter by category' }), 'Hazardous Waste')
  expect(screen.getByText('SCA-HAZ-1')).toBeTruthy()
  expect(screen.getAllByText('Hazardous Waste').length).toBeGreaterThan(0)
})
