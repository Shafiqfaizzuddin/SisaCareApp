// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { StaffTaskDetailPage } from './StaffTaskDetailPage'

const api = vi.hoisted(() => ({ getMyTask: vi.fn(), startTask: vi.fn(), submitTask: vi.fn() }))
vi.mock('../features/collection/collection-api', () => api)

const task = {
  id: 'report-1', reference: 'SCA-1', title: 'Park cleanup', summary: 'Plastic at the entrance',
  location: 'Community Hall', category: 'Recyclable Waste', created_at: '2026-10-01T00:00:00Z',
  assignment: { assignee_id: 'staff-1', team_name: 'North crew', assigned_at: '2026-10-02T00:00:00Z' },
  status_events: [],
}

beforeEach(() => { api.getMyTask.mockReset(); api.startTask.mockReset(); api.submitTask.mockReset() })
afterEach(() => cleanup())

it('starts an assigned task and requires a photo before staff submits proof', async () => {
  api.getMyTask.mockResolvedValueOnce({ ...task, status: 'assigned' })
    .mockResolvedValueOnce({ ...task, status: 'in_progress' })
    .mockResolvedValueOnce({ ...task, status: 'pending_verification' })
  api.startTask.mockResolvedValue({})
  api.submitTask.mockResolvedValue({})
  render(<MemoryRouter initialEntries={['/staff/tasks/report-1']}><Routes>
    <Route path="/staff/tasks/:reportId" element={<StaffTaskDetailPage />} />
  </Routes></MemoryRouter>)

  await userEvent.click(await screen.findByRole('button', { name: 'Start collection' }))
  await waitFor(() => expect(api.startTask).toHaveBeenCalledWith('report-1'))
  const submit = await screen.findByRole('button', { name: 'Submit for verification' }) as HTMLButtonElement
  expect(submit.disabled).toBe(true)
  await userEvent.type(screen.getByRole('textbox', { name: 'Cleanup note' }), 'Waste collected safely.')
  expect(submit.disabled).toBe(true)
  const image = new File(['proof'], 'cleanup.png', { type: 'image/png' })
  await userEvent.upload(screen.getByLabelText('Cleanup photo'), image)
  await userEvent.click(submit)
  await waitFor(() => expect(api.submitTask).toHaveBeenCalledWith('report-1', 'Waste collected safely.', image))
  expect(await screen.findByText(/An administrator will verify it/)).toBeTruthy()
})
