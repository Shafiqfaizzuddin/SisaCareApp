// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AdminDashboardPage } from './AdminDashboardPage'
import { AdminLayout } from '../layouts/AdminLayout'

const mocks = vi.hoisted(() => ({ fetchPersistedReports: vi.fn(), fetchAnalytics: vi.fn(), fetchForecast: vi.fn(), downloadAnalytics: vi.fn() }))
vi.mock('../features/admin-reports/admin-reports-api', () => ({ fetchPersistedReports: mocks.fetchPersistedReports }))
vi.mock('../features/admin-analytics/admin-analytics-api', () => ({ fetchAnalytics: mocks.fetchAnalytics,
  fetchForecast: mocks.fetchForecast, downloadAnalytics: mocks.downloadAnalytics }))
vi.mock('../components/location/GoogleMap', () => ({
  GoogleMap: ({ ariaLabel }: { ariaLabel: string }) => <div aria-label={ariaLabel} />,
  OBSERVED_DENSITY_BANDS: [
    { label: '1 report', min: 1, color: '#238b45' }, { label: '2 reports', min: 2, color: '#a1d76a' },
    { label: '3–4 reports', min: 3, color: '#fee08b' }, { label: '5–9 reports', min: 5, color: '#f46d43' },
    { label: '10+ reports', min: 10, color: '#a50026' },
  ],
}))
vi.mock('../components/admin/EmailDeliveryPanel', () => ({ EmailDeliveryPanel: () => <div>Email delivery panel</div> }))
vi.mock('../features/authentication/useRole', () => ({ useRole: () => ({ user: { name: 'Admin', title: 'Administrator' }, signOut: vi.fn() }) }))
vi.mock('../components/common/Brand', () => ({ Brand: () => <span>SisaCare.AI</span> }))
vi.mock('../components/common/ThemeToggle', () => ({ ThemeToggle: () => null }))

beforeEach(() => {
  vi.stubGlobal('Option', function Option(text: string, value: string) {
    const option = document.createElement('option'); option.text = text; option.value = value; return option
  })
  mocks.fetchAnalytics.mockReset().mockResolvedValue({ filters: {}, generated_at: '',
    metrics: { total_submitted: 4, by_status: { resolved: 3, submitted: 1 }, by_category: { 'Hazardous Waste': 4 },
      resolved_current: 3, resolution_rate_percent: 75, verified_resolution_count: 2,
      average_resolution_hours: 48, median_resolution_hours: 48, missing_coordinates: 1,
      resolved_without_verified_timestamp: 1, staff: { task_assignments: 2, active_assignments: 1,
        verified_completions_with_proof: 1, by_staff: [] } },
    trends: [{ date: '2026-10-13', reported: 4, resolved: 2 }],
    observed_heatmap: [{ cell_key: 'g1km:11299:342', center_latitude: 3.075, center_longitude: 101.525,
      south: 3.07, north: 3.08, west: 101.52, east: 101.53, count: 3 }] })
  mocks.fetchForecast.mockReset().mockResolvedValue({ status: 'available', model_version: 'weekly-grid-005-v1',
    periods: [{ start: '2026-11-02', end: '2026-11-09', cells: [{ cell_key: 'g005:61:2030', center_latitude: 3.075, center_longitude: 101.525, predicted_count: 2 }] }] })
  mocks.downloadAnalytics.mockReset().mockResolvedValue(undefined)
  mocks.fetchPersistedReports.mockReset().mockResolvedValue([{
  id: 'haz-1', reference: 'SCA-HAZ-1', category: 'Hazardous Waste', location: 'Campus Gate',
  submittedAt: '13 Oct 2026', status: 'submitted', confidence: null, description: 'Battery',
  reporter: 'Member', reporterRole: 'user', validationStatus: 'pending',
  }])
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView })

it('keeps hazardous reports in the admin list and category filter', async () => {
  render(<MemoryRouter><AdminDashboardPage /></MemoryRouter>)
  await waitFor(() => expect(screen.getByText('SCA-HAZ-1')).toBeTruthy())
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Filter by category' }), 'Hazardous Waste')
  expect(screen.getByText('SCA-HAZ-1')).toBeTruthy()
  expect(screen.getAllByText('Hazardous Waste').length).toBeGreaterThan(0)
  expect(screen.getByRole('link', { name: 'Open report SCA-HAZ-1' }).getAttribute('href')).toBe('/admin/reports/haz-1')
})

it('shows backend metrics, filters exports, and keeps forecast separate from observed density', async () => {
  render(<MemoryRouter><AdminDashboardPage /></MemoryRouter>)
  await waitFor(() => expect(screen.getByText('75%')).toBeTruthy())
  expect(screen.getByLabelText('Observed report density map')).toBeTruthy()
  expect(screen.getByLabelText('Observed report count legend')).toBeTruthy()
  await userEvent.click(await screen.findByRole('button', { name: 'g1km:11299:342' }))
  expect(screen.getByText(/Selected area .*3 reports/)).toBeTruthy()
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Filter by category' }), 'Hazardous Waste')
  await waitFor(() => expect(mocks.fetchAnalytics).toHaveBeenLastCalledWith(expect.objectContaining({ category: 'Hazardous Waste' }), expect.anything()))
  await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
  expect(mocks.downloadAnalytics).toHaveBeenCalledWith('csv', expect.objectContaining({ category: 'Hazardous Waste' }))
  await userEvent.click(screen.getByRole('button', { name: 'Forecast' }))
  expect(screen.getByLabelText('Forecast report counts map')).toBeTruthy()
  expect(screen.getByRole('columnheader', { name: 'Predicted reports' })).toBeTruthy()
  expect(screen.getByText(/category, status, submission date and observed 1 km area filters do not apply/)).toBeTruthy()
})

it('scrolls to the report section when Reports is clicked, including a repeat click', async () => {
  const scroll = vi.fn()
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: scroll })
  render(<MemoryRouter initialEntries={['/admin']}><Routes>
    <Route path="/admin" element={<AdminLayout />}>
      <Route index element={<AdminDashboardPage />} />
    </Route>
  </Routes></MemoryRouter>)
  const reportsLink = screen.getByRole('link', { name: 'Reports' })
  await userEvent.click(reportsLink)
  await waitFor(() => expect(scroll).toHaveBeenCalledTimes(1))
  expect(reportsLink.className).toContain('active')
  await userEvent.click(reportsLink)
  expect(scroll).toHaveBeenCalledTimes(2)
})

it('returns from a report detail page to the report section', async () => {
  const scroll = vi.fn()
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: scroll })
  render(<MemoryRouter initialEntries={['/admin/reports/haz-1']}><Routes>
    <Route path="/admin" element={<AdminLayout />}>
      <Route index element={<AdminDashboardPage />} />
      <Route path="reports/:reportId" element={<p>Report detail</p>} />
    </Route>
  </Routes></MemoryRouter>)
  await userEvent.click(screen.getByRole('link', { name: 'Reports' }))
  expect(await screen.findByRole('heading', { name: 'Review queue' })).toBeTruthy()
  await waitFor(() => expect(scroll).toHaveBeenCalledTimes(1))
})
