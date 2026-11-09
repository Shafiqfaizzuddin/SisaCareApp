// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const { listMyTasks } = vi.hoisted(() => ({ listMyTasks: vi.fn() }))
vi.mock('../features/collection/collection-api', () => ({ listMyTasks }))
vi.mock('../components/reports/ReportStatus', () => ({ ReportStatus: ({ status }: { status: string }) => <span>{status}</span> }))
import { StaffDashboardPage } from './StaffDashboardPage'

beforeEach(() => listMyTasks.mockReset())
afterEach(cleanup)

it('shows only tasks returned for the signed-in staff member and refreshes them', async () => {
  listMyTasks.mockResolvedValueOnce([
    { id: 'report-1', reference: 'SCA-1', title: 'Park cleanup', location: 'North park', category: 'Plastic',
      status: 'assigned', created_at: '2026-11-09T00:00:00Z', assigned_at: '2026-11-09T01:00:00Z', team_name: 'North crew' },
    { id: 'report-2', reference: 'SCA-2', title: 'River cleanup', location: 'River walk', category: 'Glass',
      status: 'in_progress', created_at: '2026-11-09T00:00:00Z', assigned_at: '2026-11-09T02:00:00Z', team_name: 'North crew' },
  ]).mockResolvedValueOnce([])
  render(<MemoryRouter><StaffDashboardPage /></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: 'Staff dashboard' })).toBeTruthy()
  expect(await screen.findByText('Park cleanup')).toBeTruthy()
  expect(screen.getByText('Plastic · North crew')).toBeTruthy()
  expect(screen.getAllByRole('link', { name: 'View task' })[0].getAttribute('href')).toBe('/staff/tasks/report-1')
  expect(screen.getByLabelText('My task summary').textContent).toContain('2Active tasks')
  await userEvent.click(screen.getByRole('button', { name: 'Refresh tasks' }))
  await waitFor(() => expect(listMyTasks).toHaveBeenCalledTimes(2))
  expect(await screen.findByText(/No active assignments yet/)).toBeTruthy()
})

