import { beforeEach, expect, it, vi } from 'vitest'

const { authenticatedFetch } = vi.hoisted(() => ({ authenticatedFetch: vi.fn() }))
vi.mock('../authentication/authenticated-fetch', () => ({ authenticatedFetch }))

import { fetchMemberDashboard } from './member-dashboard-api'

beforeEach(() => authenticatedFetch.mockReset())

it('accepts the backend submitted status for a real pending report', async () => {
  authenticatedFetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({
    points: 0, valid_reports: 0, rank: null, reports: [{ id: 'r1', reference: 'SCA-1',
      location: 'Library', status: 'submitted', validation_status: 'pending', submitted_at: '2026-10-17T10:00:00Z' }],
  }) })
  const result = await fetchMemberDashboard()
  expect(result.reports).toHaveLength(1)
  expect(result.reports[0].status).toBe('submitted')
})

it('reports expiry as authentication and still rejects malformed data', async () => {
  authenticatedFetch.mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({ detail: 'Authentication is required.' }) })
  await expect(fetchMemberDashboard()).rejects.toThrow(/session has expired/)
  authenticatedFetch.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({
    points: 0, valid_reports: 0, rank: null, reports: [{ id: 'r1', status: 'anything' }],
  }) })
  await expect(fetchMemberDashboard()).rejects.toThrow(/invalid report data/)
})

it('labels a missing legacy report date without accepting an invalid date', async () => {
  const base = { points: 0, valid_reports: 0, rank: null, reports: [{ id: 'r1', reference: 'SCA-1',
    location: 'Location not recorded', status: 'submitted', validation_status: 'pending', submitted_at: null }] }
  authenticatedFetch.mockResolvedValueOnce({ ok: true, status: 200, json: async () => base })
  expect((await fetchMemberDashboard()).reports[0].submittedAt).toBe('Date unavailable')
  authenticatedFetch.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({
    ...base, reports: [{ ...base.reports[0], submitted_at: 'not-a-date' }],
  }) })
  await expect(fetchMemberDashboard()).rejects.toThrow(/invalid report data/)
})

it('accepts the municipal status progression without accepting arbitrary statuses', async () => {
  const statuses = ['verified', 'in_progress', 'resolved', 'rejected']
  authenticatedFetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({
    points: 0, valid_reports: 0, rank: null,
    reports: statuses.map((status, index) => ({ id: String(index), reference: `SCA-${index}`,
      location: 'Community Hall', status, validation_status: status === 'rejected' ? 'invalid' : 'valid',
      submitted_at: '2026-10-18T10:00:00Z' })),
  }) })
  expect((await fetchMemberDashboard()).reports.map(report => report.status)).toEqual(statuses)
})
