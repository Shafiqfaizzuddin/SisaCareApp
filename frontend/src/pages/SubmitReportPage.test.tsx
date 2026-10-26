// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReportLocation } from '../types'
import { SubmitReportPage } from './SubmitReportPage'

const mocks = vi.hoisted(() => ({ analyze: vi.fn(), draft: vi.fn(), submit: vi.fn(), classify: vi.fn(), refresh: vi.fn() }))
vi.mock('../features/authentication/useRole', () => ({ useRole: () => ({ role: 'user', user: { id: 'person-1' }, refreshMemberData: mocks.refresh }) }))
vi.mock('../features/reporting/waste-analysis', () => ({ analyzeWasteImage: mocks.analyze, WasteAnalysisRequestError: class WasteAnalysisRequestError extends Error {} }))
vi.mock('../features/reporting/report-draft', () => ({ generateReportDraft: mocks.draft }))
vi.mock('../features/reporting/report-submission', () => ({ submitWasteReport: mocks.submit, ReportSubmissionRequestError: class ReportSubmissionRequestError extends Error {} }))
vi.mock('../features/reporting/waste-rules', () => ({ classifyConfirmedItem: mocks.classify }))
vi.mock('../components/location/LocationPicker', () => ({ LocationPicker: ({ onChange, onConfirm }: {
  onChange: (location: ReportLocation) => void, onConfirm: () => void
}) => <div data-testid="incident-map"><button type="button" onClick={() => onChange({
  latitude: 6.4, longitude: 100.2, address: 'Community Hall', source: 'map', street: null,
  city: null, state: null, postcode: null, country: null,
})}>Select pin</button><button type="button" onClick={onConfirm}>Confirm location</button></div> }))

const bottle = { id: 'det-0', label: 'plastic bottle', name: 'plastic_bottle', display_name: 'Plastic Bottle',
  bounding_box: { x1: 40, y1: 20, x2: 200, y2: 100 }, confidence: null, review_status: 'likely_waste',
  suggested_category: 'Recyclable Waste', material: 'Plastic', recommended_handling: 'Check station acceptance.',
  rule_id: 'WASTE-PLASTIC_BOTTLE-v1', station_material_key: 'Plastic' }
const food = { ...bottle, id: 'det-1', label: 'food scraps', name: 'food_waste', display_name: 'Food Waste',
  bounding_box: { x1: 210, y1: 10, x2: 300, y2: 90 }, suggested_category: 'Non-Recyclable Waste',
  material: 'Organic Material', station_material_key: null }
const uncertain = { ...bottle, id: 'det-2', label: 'bottle', name: 'bottle', display_name: 'Bottle',
  suggested_category: 'Recyclable Waste', review_status: 'likely_waste', material: 'Plastic',
  classification_source: 'vision', needs_confirmation: true,
  confirmation_reason: 'Bottle material is visually uncertain.', station_material_key: 'Plastic' }
const analysis = { success: true, analysis_id: 'analysis-1', original_image: '/api/waste/uploads/photo.jpg',
  display_image: 'blob:aligned', image_width: 400, image_height: 200, provider: 'florence2',
  model_id: 'microsoft/Florence-2-base', model_revision: 'pinned', processing_time_ms: 30,
  warnings: [], detections: [bottle, food] }
const draft = { title: 'Plastic Bottle and Food Waste', summary: 'Plastic Bottle and Food Waste were observed.',
  waste_identified: 'Plastic Bottle; Food Waste', recommended_action: 'Arrange appropriate collection.',
  environmental_concern: 'Review the reported waste.', source: 'template', model_id: '' }

beforeEach(() => {
  mocks.analyze.mockReset().mockResolvedValue(analysis)
  mocks.draft.mockReset().mockResolvedValue(draft)
  mocks.submit.mockReset().mockResolvedValue({ reference: 'SCA-1', submitted_at: '2026-10-18T00:00:00Z' })
  mocks.classify.mockReset().mockResolvedValue({ category: 'Hazardous Waste', material: 'Metal',
    handling_guidance: 'Arrange special collection.', confirmation_question: null, rule_id: 'WASTE-AEROSOL_CAN-v1',
    questions: [], station_material_key: null, classification_source: 'user_confirmed' })
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:preview')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

async function start() {
  render(<MemoryRouter><SubmitReportPage /></MemoryRouter>)
  await userEvent.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!,
    new File(['photo'], 'waste.jpg', { type: 'image/jpeg' }))
  await waitFor(() => expect(mocks.draft).toHaveBeenCalledTimes(1))
}

describe('streamlined waste report', () => {
  it('drafts automatically once, keeps mixed categories, and needs no item confirmation', async () => {
    await start()
    expect(mocks.analyze).toHaveBeenCalledTimes(1)
    expect(mocks.draft).toHaveBeenCalledTimes(1)
    expect(mocks.draft.mock.calls[0][0].confirmed_items.map((item: { category: string }) => item.category))
      .toEqual(['Recyclable Waste', 'Non-Recyclable Waste'])
    await waitFor(() => expect((screen.getByRole('textbox', { name: 'Title' }) as HTMLInputElement).value).toBe(draft.title))
    expect(screen.queryByRole('button', { name: 'Confirm reviewed items' })).toBeNull()
    expect(screen.getAllByText(/AI-generated details may contain errors/).length).toBeGreaterThan(0)
    expect(mocks.submit).not.toHaveBeenCalled()
    expect(screen.queryByText('Editable preview')).toBeNull()
  })

  it('shows one compact group for ten detections while retaining ten outlines', async () => {
    mocks.analyze.mockResolvedValue({ ...analysis, detections: Array.from({ length: 10 }, (_, index) => ({
      ...uncertain, id: `det-${index}`, label: index % 2 ? 'plastic bag' : 'plastic film',
      name: index % 2 ? 'plastic_bag' : 'plastic_film', display_name: index % 2 ? 'Plastic Bag' : 'Plastic Film',
      material: 'Soft Plastic', suggested_category: 'Non-Recyclable Waste', review_status: 'likely_waste',
      rule_id: index % 2 ? 'COMMUNITY-PLASTIC_BAG-v1' : 'COMMUNITY-PLASTIC_FILM-v1',
      confirmation_question: null, confirmation_reason: null, needs_confirmation: false,
    })) })
    await start()
    expect(screen.getAllByText('10 detections')).toHaveLength(1)
    expect(document.querySelectorAll('svg[aria-label="Detected object outlines"] rect')).toHaveLength(10)
    expect(screen.getAllByText('Plastic Bags / Film').length).toBeGreaterThan(0)
    expect(screen.queryByText('10 items')).toBeNull()
  })

  it('keeps uncertain items and drafts without location', async () => {
    mocks.analyze.mockResolvedValue({ ...analysis, detections: [uncertain] })
    await start()
    expect(mocks.draft.mock.calls[0][0].confirmed_address).toBe('')
    expect(mocks.draft.mock.calls[0][0].confirmed_items[0].category).toBe('Recyclable Waste')
    expect(screen.getByText(/AI note: Bottle material is visually uncertain/)).toBeTruthy()
    expect(screen.queryByTestId('incident-map')).toBeNull()
  })

  it('drafts for an image with no detections and allows admin assessment', async () => {
    mocks.analyze.mockResolvedValue({ ...analysis, detections: [] })
    mocks.draft.mockResolvedValue({ ...draft, title: 'Unidentified waste', summary: 'No objects were identified.' })
    await start()
    expect(mocks.draft.mock.calls[0][0].confirmed_items).toEqual([])
    expect(screen.getByText(/No objects were detected/)).toBeTruthy()
    expect(screen.getByText(/Unidentified waste/)).toBeTruthy()
  })

  it('keeps the photo and manual reporting option when detection fails', async () => {
    mocks.analyze.mockRejectedValue(new Error('service unavailable'))
    render(<MemoryRouter><SubmitReportPage /></MemoryRouter>)
    await userEvent.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!,
      new File(['photo'], 'waste.jpg', { type: 'image/jpeg' }))
    await waitFor(() => expect(screen.getByText(/Photo analysis failed/)).toBeTruthy())
    expect(screen.getByAltText('Selected waste')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Retry analysis' })).toBeTruthy()
    expect(screen.queryByRole('textbox', { name: 'Title' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Write a manual report instead' }))
    expect(screen.getByRole('textbox', { name: 'Title' })).toBeTruthy()
    expect(mocks.draft).not.toHaveBeenCalled()
  })

  it('keeps corrections optional and reruns mapping after an edit', async () => {
    await start()
    const details = screen.getByText('Edit analysis / Add details').closest('details')!
    expect(details.open).toBe(false)
    await userEvent.click(screen.getByText('Edit analysis / Add details'))
    expect(details.open).toBe(true)
    const label = screen.getAllByRole('textbox', { name: 'Correct item label' })[0]
    await userEvent.clear(label)
    await userEvent.type(label, 'Aerosol Can')
    await userEvent.tab()
    await waitFor(() => expect(mocks.classify).toHaveBeenCalledWith('Aerosol Can', 'Unknown', {}))
    expect(screen.getByText(/Regenerate the draft if you want updated suggestions/)).toBeTruthy()
  })

  it('does not overwrite a typed title on regeneration', async () => {
    mocks.draft.mockResolvedValueOnce(draft).mockResolvedValueOnce({ ...draft, title: 'New AI title' })
    await start()
    const title = screen.getByRole('textbox', { name: 'Title' })
    await userEvent.clear(title)
    await userEvent.type(title, 'My own report title')
    await userEvent.click(screen.getByRole('button', { name: 'Regenerate report draft' }))
    await waitFor(() => expect(mocks.draft).toHaveBeenCalledTimes(2))
    expect((title as HTMLInputElement).value).toBe('My own report title')
    await userEvent.click(screen.getByText('View generated suggestion'))
    await screen.findByText('New AI title')
    await userEvent.click(screen.getByRole('button', { name: 'Use suggested title' }))
    expect((title as HTMLInputElement).value).toBe('New AI title')
  })

  it('keeps a user-written description on regeneration', async () => {
    mocks.draft.mockResolvedValueOnce(draft).mockResolvedValueOnce({ ...draft, summary: 'Replacement suggestion' })
    await start()
    const description = screen.getByRole('textbox', { name: 'Report description' }) as HTMLTextAreaElement
    await userEvent.clear(description)
    await userEvent.type(description, 'My own description of the waste.')
    await userEvent.click(screen.getByRole('button', { name: 'Regenerate report draft' }))
    await waitFor(() => expect(mocks.draft).toHaveBeenCalledTimes(2))
    expect(description.value).toBe('My own description of the waste.')
  })

  it('requires one location before submission and retains categories', async () => {
    await start()
    expect((screen.getByRole('button', { name: 'Submit report' }) as HTMLButtonElement).disabled).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: 'Choose location' }))
    expect(screen.getAllByTestId('incident-map')).toHaveLength(1)
    await userEvent.click(screen.getByRole('button', { name: 'Select pin' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm location' }))
    await userEvent.click(screen.getByRole('button', { name: 'Submit report' }))
    await waitFor(() => expect(mocks.submit).toHaveBeenCalledTimes(1))
    expect(mocks.submit.mock.calls[0][0].category).toBe('Non-Recyclable Waste')
    expect(mocks.submit.mock.calls[0][0].confirmed_items).toHaveLength(2)
    expect(mocks.submit.mock.calls[0][0].draft_source).toBe('template')
  })
})
