// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReportLocation } from '../types'
import { SubmitReportPage } from './SubmitReportPage'

const pageMocks = vi.hoisted(() => ({ analyzeWasteImage: vi.fn(), submitWasteReport: vi.fn(), generateReportDraft: vi.fn(), fetchRecyclingPoints: vi.fn(), classifyConfirmedItem: vi.fn() }))
vi.mock('../features/authentication/useRole', () => ({ useRole: () => ({ role: 'user', user: { id: 'usr-204' }, refreshMemberData: vi.fn() }) }))
vi.mock('../features/reporting/waste-analysis', () => ({ analyzeWasteImage: pageMocks.analyzeWasteImage, WasteAnalysisRequestError: class WasteAnalysisRequestError extends Error {} }))
vi.mock('../features/reporting/report-submission', () => ({ submitWasteReport: pageMocks.submitWasteReport, ReportSubmissionRequestError: class ReportSubmissionRequestError extends Error {} }))
vi.mock('../features/reporting/report-draft', () => ({ generateReportDraft: pageMocks.generateReportDraft }))
vi.mock('../features/reporting/recycling-points', () => ({ fetchRecyclingPoints: pageMocks.fetchRecyclingPoints }))
vi.mock('../features/reporting/waste-rules', () => ({ classifyConfirmedItem: pageMocks.classifyConfirmedItem }))
vi.mock('../components/location/LocationPicker', () => ({ LocationPicker: ({ value, onChange, onConfirm, onCancel }: {
  value: ReportLocation | null, onChange: (location: ReportLocation) => void, onConfirm: () => void, onCancel: () => void
}) => <div data-testid="incident-map"><span>{value?.address ?? 'No selection'}</span>
  <button type="button" onClick={() => onChange({ latitude: 6.4, longitude: 100.2, address: 'Campus', street: null, city: null, state: null, postcode: null, country: null, source: 'map' })}>Select campus</button>
  <button type="button" onClick={onConfirm}>Confirm location</button><button type="button" onClick={onCancel}>Cancel</button></div> }))

const analysis = { success: true, analysis_id: 'draft-123', original_image: '/api/waste/uploads/photo.jpg', display_image: 'blob:oriented',
  image_width: 400, image_height: 200, provider: 'florence2', model_id: 'microsoft/Florence-2-base', model_revision: 'pinned', processing_time_ms: 30, warnings: [],
  detections: [
    { id: 'det-0', label: 'plastic bottle', name: 'plastic_bottle', display_name: 'Plastic Bottle', bounding_box: { x1: 40, y1: 20, x2: 200, y2: 100 }, confidence: null, review_status: 'likely_waste', suggested_category: 'Recyclable Waste', material: 'Plastic', recommended_handling: 'Recycle.' },
    { id: 'det-1', label: 'tree', name: 'tree', display_name: 'Tree', bounding_box: { x1: 210, y1: 10, x2: 390, y2: 190 }, confidence: null, review_status: 'background', suggested_category: null, material: 'Unknown', recommended_handling: 'Confirm.' },
  ] }

beforeEach(() => {
  pageMocks.analyzeWasteImage.mockReset().mockResolvedValue(analysis)
  pageMocks.submitWasteReport.mockReset()
  pageMocks.generateReportDraft.mockReset()
  pageMocks.classifyConfirmedItem.mockReset().mockResolvedValue({ category: 'Hazardous Waste', material: 'Mixed Material',
    handling_guidance: 'Keep the battery separate for staff collection.', confirmation_reason: null,
    rule_id: 'WASTE-BATTERY-v1', questions: [], station_material_key: null })
  pageMocks.fetchRecyclingPoints.mockReset().mockResolvedValue([{ id: 'station-1', name: 'Campus station', latitude: 6.4, longitude: 100.2,
    accepted_materials: ['Plastic'], description: '', active: true }])
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:preview')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

async function upload() {
  await userEvent.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!, new File(['photo'], 'waste.jpg', { type: 'image/jpeg' }))
}

describe('SubmitReportPage Florence review', () => {
  it('draws raw pixel boxes over the oriented image and keeps background objects visible', async () => {
    render(<MemoryRouter><SubmitReportPage /></MemoryRouter>)
    await upload()
    await userEvent.click(screen.getByRole('button', { name: 'Analyze photo' }))
    await screen.findByText(/2 objects to review/)
    const svg = screen.getByLabelText('Detected object outlines')
    expect(svg.getAttribute('viewBox')).toBe('0 0 400 200')
    expect(svg.querySelector('rect')?.getAttribute('x')).toBe('40')
    expect(screen.getByText(/Model label: tree/)).toBeTruthy()
    await userEvent.click(screen.getByRole('checkbox', { name: 'Show object outlines' }))
    expect(screen.queryByLabelText('Detected object outlines')).toBeNull()
  })

  it('offers manual identification after a service failure while retaining photo and report fields', async () => {
    pageMocks.analyzeWasteImage.mockRejectedValue(new Error('Timed out'))
    render(<MemoryRouter><SubmitReportPage /></MemoryRouter>)
    await upload()
    await userEvent.click(screen.getByRole('button', { name: 'Identify items manually' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Title' }), 'Campus litter')
    await userEvent.click(screen.getByRole('button', { name: 'Analyze photo' }))
    await screen.findByText(/Analysis could not be completed/)
    expect(screen.getAllByText('waste.jpg').length).toBeGreaterThan(0)
    expect((screen.getByRole('textbox', { name: 'Title' }) as HTMLInputElement).value).toBe('Campus litter')
    await userEvent.click(screen.getByRole('button', { name: 'Add missed waste item' }))
    expect(screen.getByRole('textbox', { name: 'Correct item label' })).toBeTruthy()
  })

  it('keeps one collapsible report-location picker independent of analysis', async () => {
    render(<MemoryRouter><SubmitReportPage /></MemoryRouter>)
    await userEvent.click(screen.getByRole('button', { name: 'Choose location' }))
    expect(screen.getAllByTestId('incident-map')).toHaveLength(1)
    await userEvent.click(screen.getByRole('button', { name: 'Select campus' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm location' }))
    expect(screen.queryByTestId('incident-map')).toBeNull()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Edit location' })).toBeTruthy())
    expect(pageMocks.analyzeWasteImage).not.toHaveBeenCalled()
  })

  it('submits corrections, removed background and a missed item with mixed categories', async () => {
    pageMocks.submitWasteReport.mockResolvedValue({ reference: 'REF-1', submitted_at: 'now' })
    render(<MemoryRouter><SubmitReportPage /></MemoryRouter>)
    await upload()
    await userEvent.click(screen.getByRole('button', { name: 'Analyze photo' }))
    await screen.findByText(/2 objects to review/)
    const labels = screen.getAllByRole('textbox', { name: 'Correct item label' })
    await userEvent.clear(labels[0])
    await userEvent.type(labels[0], 'Battery')
    const materials = screen.getAllByRole('textbox', { name: 'Confirmed material' })
    await userEvent.clear(materials[0])
    await userEvent.type(materials[0], 'Unknown')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Confirmed category' }), 'Hazardous Waste')
    await userEvent.selectOptions(screen.getAllByRole('combobox', { name: 'Review decision' })[1], 'removed')
    await userEvent.click(screen.getAllByRole('checkbox', { name: 'I confirm this decision' })[0])
    await userEvent.click(screen.getAllByRole('checkbox', { name: 'I confirm this decision' })[1])
    await userEvent.click(screen.getByRole('button', { name: 'Add missed waste item' }))
    await userEvent.type(screen.getAllByRole('textbox', { name: 'Correct item label' })[2], 'Plastic Bottle')
    await userEvent.type(screen.getAllByRole('textbox', { name: 'Confirmed material' })[1], 'Plastic')
    await userEvent.selectOptions(screen.getAllByRole('combobox', { name: 'Confirmed category' })[1], 'Recyclable Waste')
    await userEvent.click(screen.getAllByRole('checkbox', { name: 'I confirm this decision' })[2])
    expect(screen.getByText(/Primary report category: Hazardous Waste/)).toBeTruthy()
    expect(screen.getByText(/Confirmed item categories: Hazardous Waste, Recyclable Waste/)).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Report all items to staff' }))
    for (const [label, value] of [['Title', 'Mixed waste'], ['Summary', 'A battery and bottle'], ['Waste identified', 'Battery and bottle'], ['Recommended action', 'Collect separately'], ['Environmental concern', 'Litter']] as const) {
      await userEvent.type(screen.getByRole('textbox', { name: label }), value)
    }
    await userEvent.click(screen.getByRole('button', { name: 'Choose location' }))
    await userEvent.click(screen.getByRole('button', { name: 'Select campus' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm location' }))
    await userEvent.click(screen.getByRole('checkbox', { name: /I confirm this report is accurate/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Submit report' }))
    await waitFor(() => expect(pageMocks.submitWasteReport).toHaveBeenCalledOnce())
    const payload = pageMocks.submitWasteReport.mock.calls[0][0]
    expect(payload.category).toBe('Hazardous Waste')
    expect(payload.confirmed_items.map((item: { name: string }) => item.name)).toEqual(['Battery', 'Plastic Bottle'])
    expect(payload.reviewed_detections.map((item: { disposition: string }) => item.disposition)).toEqual(['waste', 'removed', 'waste'])
    expect(payload.reviewed_detections[2].source_detection_id).toBeNull()
  })

  it('drafts only after review and preserves manual edits when regenerated with a location', async () => {
    pageMocks.generateReportDraft
      .mockResolvedValueOnce({ title: 'Plastic Bottle report', summary: 'Plastic Bottle at the site.',
        waste_identified: 'Plastic Bottle', recommended_action: 'Use reviewed guidance.',
        environmental_concern: 'May affect the area.', source: 'ollama', model_id: 'llama3.2' })
      .mockResolvedValueOnce({ title: 'Updated Plastic Bottle report', summary: 'Plastic Bottle near Campus.',
        waste_identified: 'Plastic Bottle', recommended_action: 'Use reviewed guidance.',
        environmental_concern: 'May affect the area.', source: 'ollama', model_id: 'llama3.2' })
    render(<MemoryRouter><SubmitReportPage /></MemoryRouter>)
    await upload()
    await userEvent.click(screen.getByRole('button', { name: 'Analyze photo' }))
    await screen.findByText(/2 objects to review/)
    for (const box of screen.getAllByRole('checkbox', { name: 'I confirm this decision' })) await userEvent.click(box)
    await userEvent.click(screen.getByRole('button', { name: 'Report It Instead' }))
    await userEvent.click(screen.getByRole('button', { name: 'Generate report draft' }))
    await screen.findByText(/Local Ollama/)
    expect(pageMocks.generateReportDraft.mock.calls[0][0].confirmed_address).toBe('')
    const title = screen.getByRole('textbox', { name: 'Title' }) as HTMLInputElement
    await userEvent.clear(title)
    await userEvent.type(title, 'My own title')
    await userEvent.click(screen.getByRole('button', { name: 'Choose location' }))
    await userEvent.click(screen.getByRole('button', { name: 'Select campus' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm location' }))
    await userEvent.click(screen.getByRole('button', { name: 'Regenerate report draft' }))
    await screen.findByText(/Updated Plastic Bottle report/)
    expect(pageMocks.generateReportDraft.mock.calls[1][0].confirmed_address).toBe('Campus')
    expect(title.value).toBe('My own title')
    expect((screen.getByRole('textbox', { name: 'Summary' }) as HTMLTextAreaElement).value).toBe('Plastic Bottle near Campus.')
    expect(pageMocks.submitWasteReport).not.toHaveBeenCalled()
  })

  it('shows stations for the recyclable subset of a hazardous mixed photo without hazardous proof', async () => {
    pageMocks.analyzeWasteImage.mockResolvedValue({ ...analysis, detections: [
      { ...analysis.detections[0], station_material_key: 'Plastic', rule_id: 'WASTE-PLASTIC_BOTTLE-v1' },
      { ...analysis.detections[1], id: 'det-1', label: 'battery', name: 'battery', display_name: 'Battery',
        suggested_category: 'Hazardous Waste', material: 'Mixed Material', review_status: 'likely_waste',
        recommended_handling: 'Keep battery separate for appropriate collection.', rule_id: 'WASTE-BATTERY-v1' },
    ] })
    render(<MemoryRouter><SubmitReportPage /></MemoryRouter>)
    await upload()
    await userEvent.click(screen.getByRole('button', { name: 'Analyze photo' }))
    await screen.findByText(/2 objects to review/)
    for (const box of screen.getAllByRole('checkbox', { name: 'I confirm this decision' })) await userEvent.click(box)
    expect(screen.getByText(/Keep battery separate for appropriate collection/)).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Stations for recyclable items' }))
    await screen.findByText('Campus station')
    expect(screen.getByText(/separate photo of the recyclable items/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Submit for admin verification' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Report all items to staff' })).toBeTruthy()
  })

  it('refreshes a corrected item through the maintained waste rules', async () => {
    render(<MemoryRouter><SubmitReportPage /></MemoryRouter>)
    await upload()
    await userEvent.click(screen.getByRole('button', { name: 'Analyze photo' }))
    await screen.findByText(/2 objects to review/)
    const label = screen.getAllByRole('textbox', { name: 'Correct item label' })[0]
    await userEvent.clear(label)
    await userEvent.type(label, 'Battery')
    await userEvent.click(screen.getByRole('button', { name: 'Apply waste rules' }))
    await screen.findByText(/Keep the battery separate for staff collection/)
    expect(pageMocks.classifyConfirmedItem).toHaveBeenCalledWith('Battery', 'Unknown', {})
    expect((screen.getByRole('combobox', { name: 'Confirmed category' }) as HTMLSelectElement).value).toBe('Hazardous Waste')
  })

  it('requires a fresh rule decision when a confirmed condition changes', async () => {
    pageMocks.classifyConfirmedItem.mockResolvedValueOnce({ category: 'Hazardous Waste', material: 'Plastic',
      handling_guidance: 'Keep the confirmed hazardous container separate for staff collection.', confirmation_reason: null,
      rule_id: 'WASTE-PLASTIC_BOTTLE-v1', questions: [], station_material_key: null })
    pageMocks.analyzeWasteImage.mockResolvedValue({ ...analysis, detections: [{ ...analysis.detections[0],
      questions: [{ key: 'hazardous_contents', prompt: 'Did this item contain chemicals or another hazardous substance?' }],
      station_material_key: 'Plastic',
    }] })
    render(<MemoryRouter><SubmitReportPage /></MemoryRouter>)
    await upload()
    await userEvent.click(screen.getByRole('button', { name: 'Analyze photo' }))
    await screen.findByText(/1 objects to review/)
    await userEvent.selectOptions(screen.getByRole('combobox', { name: /Did this item contain chemicals/ }), 'true')
    expect((screen.getByRole('combobox', { name: 'Confirmed category' }) as HTMLSelectElement).value).toBe('')
    await userEvent.click(screen.getByRole('button', { name: 'Apply waste rules' }))
    await screen.findByText(/Keep the confirmed hazardous container separate for staff collection/)
    expect(pageMocks.classifyConfirmedItem).toHaveBeenCalledWith('Plastic Bottle', 'Plastic', { hazardous_contents: true })
    expect((screen.getByRole('combobox', { name: 'Confirmed category' }) as HTMLSelectElement).value).toBe('Hazardous Waste')
  })
})
