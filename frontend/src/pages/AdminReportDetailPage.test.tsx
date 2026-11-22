// @vitest-environment happy-dom

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AdminReportDetail } from '../types'
import { AdminReportDetailPage } from './AdminReportDetailPage'


const pageMocks = vi.hoisted(() => ({
  fetchPersistedReport: vi.fn(),
  validatePersistedReport: vi.fn(),
  assignPersistedReport: vi.fn(),
  listStaff: vi.fn(),
  reviewTask: vi.fn(),
}))

vi.mock('../features/admin-reports/admin-reports-api', () => ({
  fetchPersistedReport: pageMocks.fetchPersistedReport,
  validatePersistedReport: pageMocks.validatePersistedReport,
  assignPersistedReport: pageMocks.assignPersistedReport,
}))

vi.mock('../features/collection/collection-api', () => ({
  listStaff: pageMocks.listStaff,
  reviewTask: pageMocks.reviewTask,
}))

vi.mock('../components/location/GoogleMap', () => ({
  GoogleMap: ({ ariaLabel }: { ariaLabel: string }) => (
    <div aria-label={ariaLabel}>Google map</div>
  ),
}))

const REPORT: AdminReportDetail = {
  id: 'stored-report',
  reference: 'SCA-26001',
  category: 'recyclable',
  location: 'Community Hall, Arau, Perlis',
  reportLocation: {
    latitude: 6.4436,
    longitude: 100.27,
    address: 'Community Hall, Jalan Arau, 02600 Arau, Perlis',
    street: 'Jalan Arau',
    city: 'Arau',
    state: 'Perlis',
    postcode: '02600',
    country: 'Malaysia',
    source: 'map',
  },
  siteNotes: 'Beside the entrance.',
  status: 'processing',
  validationStatus: 'pending',
  rewardPoints: 0,
  reporterRole: 'user',
  reporter: 'usr-204',
  title: 'Final edited title',
  summary: 'Final edited summary',
  wasteIdentified: 'Two plastic bottles and one mattress.',
  recommendedAction: 'Arrange the appropriate collections.',
  environmentalConcern: 'The waste may obstruct the walkway.',
  generatedReport: {
    title: 'Original AI title',
    summary: 'Original AI summary',
    waste_identified: 'Plastic bottles and mattress.',
    recommended_action: 'Collect the identified waste.',
    environmental_concern: 'The waste may cause local litter.',
  },
  finalCategories: ['Recyclable Waste', 'Bulky Waste'],
  aiAnalysis: { mode: 'hybrid' },
      confirmedItems: [{ name: 'Plastic Bottle', category: 'Recyclable Waste', material: 'Plastic' }],
      groupedReportItems: [{ canonical_name: 'plastic_bottle', display_name: 'Plastic Bottle', material: 'Plastic', category: 'Recyclable Waste', uncertainty_reason: null, detection_count: 1, detection_ids: ['det-1'] }],
  originalImage: 'blob:original',
  annotatedImage: 'blob:annotated',
  createdAt: '2026-10-06T08:00:00+00:00',
  updatedAt: '2026-10-06T08:00:00+00:00',
  detections: [
    {
      id: 'det-1',
      className: 'plastic_bottle',
      displayName: 'Plastic Bottle',
      wasteCategory: 'Recyclable Waste',
      material: 'Plastic',
      confidence: 0.92,
      boundingBox: { x1: 1, y1: 2, x2: 3, y2: 4 },
      source: 'yolo+vlm',
      createdAt: '2026-10-06T08:00:00+00:00',
    },
    {
      id: 'det-2',
      className: 'mattress',
      displayName: 'Mattress',
      wasteCategory: 'Bulky Waste',
      material: 'Mixed Bedding Material',
      confidence: null,
      boundingBox: null,
      source: 'vlm',
      createdAt: '2026-10-06T08:00:00+00:00',
    },
  ],
}

beforeEach(() => {
  pageMocks.fetchPersistedReport.mockReset()
  pageMocks.validatePersistedReport.mockReset()
  pageMocks.assignPersistedReport.mockReset()
  pageMocks.listStaff.mockReset()
  pageMocks.listStaff.mockResolvedValue([])
  pageMocks.reviewTask.mockReset()
  pageMocks.fetchPersistedReport.mockResolvedValue(REPORT)
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('AdminReportDetailPage', () => {
  it('assigns a verified report to an individual staff member without a team field', async () => {
    pageMocks.fetchPersistedReport.mockResolvedValue({
      ...REPORT, status: 'verified', validationStatus: 'valid', activeAssigneeId: null,
    })
    pageMocks.listStaff.mockResolvedValue([{ user_id: 'staff-1', role: 'staff', revoked_at: null, display_name: 'Alex Staff' }])
    pageMocks.assignPersistedReport.mockResolvedValue(undefined)
    render(<MemoryRouter initialEntries={['/admin/reports/stored-report']}><Routes>
      <Route path="/admin/reports/:reportId" element={<AdminReportDetailPage />} />
    </Routes></MemoryRouter>)
    const selector = await screen.findByLabelText('Assign to staff member or driver')
    expect(screen.queryByLabelText(/assign to team/i)).toBeNull()
    expect((screen.getByRole('button', { name: 'Assign report' }) as HTMLButtonElement).disabled).toBe(true)
    await userEvent.selectOptions(selector, 'staff-1')
    await userEvent.click(screen.getByRole('button', { name: 'Assign report' }))
    await waitFor(() => expect(pageMocks.assignPersistedReport).toHaveBeenCalledWith('stored-report', 'staff-1', ''))
  })

  it('shows persisted evidence, grouped AI facts, final text, draft, and location', async () => {
    render(
      <MemoryRouter initialEntries={['/admin/reports/stored-report']}>
        <Routes>
          <Route
            path="/admin/reports/:reportId"
            element={<AdminReportDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('SCA-26001')).toBeTruthy()
    })
    expect(screen.getByAltText('Original uploaded waste evidence')).toBeTruthy()
    expect(screen.getByAltText('Analysis evidence preview')).toBeTruthy()
    expect(screen.getByText('Reported analysis items')).toBeTruthy()
    expect(screen.getByText(/AI\/rule suggestion/)).toBeTruthy()
    expect(screen.getByText('AI and rule suggestions')).toBeTruthy()
    expect(screen.getAllByText('Plastic Bottle').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Recyclable Waste').length).toBeGreaterThan(0)
    expect(screen.getByText('YOLO + VLM')).toBeTruthy()
    expect(screen.getByText('Quantity not established')).toBeTruthy()
    expect(screen.getByText('Final submitted report')).toBeTruthy()
    expect(screen.getByText('Final edited title')).toBeTruthy()
    expect(screen.getByText('Original AI-generated draft')).toBeTruthy()
    expect(screen.getByText('Original AI title')).toBeTruthy()
    expect(screen.getByLabelText('Submitted waste report location')).toBeTruthy()
    expect(
      screen.getAllByText('Community Hall, Jalan Arau, 02600 Arau, Perlis')
        .length,
    ).toBeGreaterThan(0)
    expect(screen.getByText('6.443600, 100.270000')).toBeTruthy()
    expect(screen.getByText('processing')).toBeTruthy()
    expect(pageMocks.validatePersistedReport).not.toHaveBeenCalled()
  })
})
