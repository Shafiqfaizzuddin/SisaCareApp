// @vitest-environment happy-dom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { WasteAnalysisSuccess } from '../types'
import { SubmitReportPage } from './SubmitReportPage'


const pageMocks = vi.hoisted(() => ({
  analyzeWasteImage: vi.fn(),
  submitWasteReport: vi.fn(),
}))

vi.mock('../features/authentication/useRole', () => ({
  useRole: () => ({
    role: 'user',
    user: {
      id: 'usr-204',
      name: 'Test Member',
      email: 'member@example.com',
    },
    refreshMemberData: vi.fn(),
  }),
}))

vi.mock('../features/reporting/waste-analysis', () => ({
  analyzeWasteImage: pageMocks.analyzeWasteImage,
  WasteAnalysisRequestError: class WasteAnalysisRequestError extends Error {},
}))

vi.mock('../features/reporting/report-submission', () => ({
  submitWasteReport: pageMocks.submitWasteReport,
  ReportSubmissionRequestError: class ReportSubmissionRequestError extends Error {},
}))

vi.mock('../components/location/LocationPicker', () => ({
  LocationPicker: ({ onChange, onConfirm }: {
    onChange: (value: unknown) => void
    onConfirm: () => void
  }) => <div>
    <button type="button" onClick={() => onChange({
      latitude: 6.4436, longitude: 100.27, address: 'Test campus location',
      street: null, city: 'Arau', state: 'Perlis', postcode: null,
      country: 'Malaysia', source: 'map',
    })}>Select test location</button>
    <button type="button" onClick={onConfirm}>Confirm test location</button>
  </div>,
}))

const ANALYSIS_RESULT: WasteAnalysisSuccess = {
  success: true,
  analysis_id: 'draft-123',
  original_image: '/api/waste/uploads/upload.jpg',
  annotated_image: null,
  detections: [
    {
      name: 'plastic_bottle',
      display_name: 'Plastic Bottle',
      category: 'Recyclable Waste',
      category_source: 'mapping',
      source: 'yolo+vlm',
      confidence: 0.91,
      confidence_level: null,
      supported_by_vlm: true,
      bounding_box: { x1: 1, y1: 2, x2: 3, y2: 4 },
    },
  ],
  grouped_objects: [
    {
      name: 'plastic_bottle',
      label: 'Plastic Bottle',
      count: 1,
      category: 'Recyclable Waste',
      sources: ['yolo', 'vlm'],
      average_yolo_confidence: 0.91,
    },
  ],
  categories_detected: ['Recyclable Waste'],
  scene_description: 'A plastic bottle is visible.',
  report: {
    title: 'Generated title',
    summary: 'Generated summary',
    waste_identified: 'Plastic Bottle (count: 1)',
    recommended_action: 'Generated recommendation',
    environmental_concern: 'Generated concern may apply.',
  },
}

beforeEach(() => {
  pageMocks.analyzeWasteImage.mockReset()
  pageMocks.submitWasteReport.mockReset()
  pageMocks.analyzeWasteImage.mockResolvedValue(ANALYSIS_RESULT)
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:preview')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('SubmitReportPage hybrid draft', () => {
  it('analyzes a photo without a location, GPS permission, or map request', async () => {
    render(<MemoryRouter><SubmitReportPage /></MemoryRouter>)
    await userEvent.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!,
      new File(['photo'], 'waste.jpg', { type: 'image/jpeg' }))
    const analyze = screen.getByRole('button', { name: /analyze waste/i }) as HTMLButtonElement
    expect(analyze.disabled).toBe(false)
    await userEvent.click(analyze)
    expect(await screen.findByText('Analysis complete')).toBeTruthy()
    expect(pageMocks.analyzeWasteImage).toHaveBeenCalledOnce()
    expect((screen.getByRole('button', { name: /submit report/i }) as HTMLButtonElement).disabled).toBe(true)
  })
  it('submits mixed confirmed items as a campus report without recycling routing', async () => {
    pageMocks.analyzeWasteImage.mockResolvedValue({
      ...ANALYSIS_RESULT,
      detections: [
        { ...ANALYSIS_RESULT.detections[0], material: 'Plastic', rule_known: true },
        {
          ...ANALYSIS_RESULT.detections[0], name: 'food_wrapper', display_name: 'Food Wrapper',
          category: 'Non-Recyclable', material: 'Mixed Packaging Material',
          recyclable: false, rule_known: true,
        },
      ],
    })
    pageMocks.submitWasteReport.mockResolvedValue({
      id: 'report-1', reference: 'SCA-TEST', status: 'submitted',
      submitted_at: '2026-10-11T00:00:00Z', original_image: '', annotated_image: '',
    })
    render(<MemoryRouter><SubmitReportPage /></MemoryRouter>)
    await userEvent.upload(
      document.querySelector<HTMLInputElement>('input[type="file"]')!,
      new File(['photo'], 'waste.jpg', { type: 'image/jpeg' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Select test location' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm test location' }))
    await userEvent.click(screen.getByRole('button', { name: /analyze waste/i }))
    expect(await screen.findByText('Confirmed overall category: Non-Recyclable Waste')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Recycle It' })).toBeNull()
    await userEvent.click(screen.getByRole('checkbox'))
    const form = document.querySelector('form')!
    expect(form.checkValidity()).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: /submit report/i }))
    await waitFor(() => expect(pageMocks.submitWasteReport).toHaveBeenCalledOnce())
    const payload = pageMocks.submitWasteReport.mock.calls[0][0]
    expect(payload.category).toBe('Non-Recyclable Waste')
    expect(payload.confirmed_items).toHaveLength(2)
    expect(payload.analysis_id).toBe('draft-123')
    expect(payload.latitude).toBe(6.4436)
  })

  it('keeps all generated report fields editable without exposing raw detections', async () => {
    render(
      <MemoryRouter>
        <SubmitReportPage />
      </MemoryRouter>,
    )
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')
    expect(fileInput).not.toBeNull()
    fireEvent.change(fileInput!, {
      target: {
        files: [new File(['first'], 'first.jpg', { type: 'image/jpeg' })],
      },
    })
    await userEvent.click(screen.getByRole('button', { name: 'Select test location' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm test location' }))
    await userEvent.click(screen.getByRole('button', { name: /analyze waste/i }))

    const edits = {
      Title: 'Edited title',
      Summary: 'Edited summary',
      'Waste identified': 'Edited identified waste',
      'Recommended action': 'Edited recommendation',
      'Environmental concern': 'Edited environmental concern',
    }
    for (const [label, editedValue] of Object.entries(edits)) {
      const field = await screen.findByLabelText(label)
      fireEvent.change(field, { target: { value: editedValue } })
      expect((field as HTMLInputElement | HTMLTextAreaElement).value).toBe(
        editedValue,
      )
    }

    expect(screen.getByText('Plastic Bottle')).toBeTruthy()
    expect(screen.queryByLabelText(/confidence/i)).toBeNull()
    expect(screen.queryByLabelText(/bounding box/i)).toBeNull()
    expect(screen.queryByLabelText(/source/i)).toBeNull()
  })

  it('invalidates detections, grouping, and generated text when the image changes', async () => {
    render(
      <MemoryRouter>
        <SubmitReportPage />
      </MemoryRouter>,
    )
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')
    fireEvent.change(fileInput!, {
      target: {
        files: [new File(['first'], 'first.jpg', { type: 'image/jpeg' })],
      },
    })
    await userEvent.click(screen.getByRole('button', { name: 'Select test location' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm test location' }))
    await userEvent.click(screen.getByRole('button', { name: /analyze waste/i }))
    expect((await screen.findByLabelText('Title') as HTMLInputElement).value).toBe(
      'Generated title',
    )
    expect(screen.getByText('Analysis complete')).toBeTruthy()

    fireEvent.change(fileInput!, {
      target: {
        files: [new File(['second'], 'second.jpg', { type: 'image/jpeg' })],
      },
    })

    await waitFor(() => {
      expect(screen.queryByLabelText('Title')).toBeNull()
      expect(screen.queryByText('Analysis complete')).toBeNull()
      expect(screen.queryByText('Detected by AI')).toBeNull()
    })
    expect(pageMocks.analyzeWasteImage).toHaveBeenCalledOnce()
    expect(
      (screen.getByRole('button', {
        name: /analyze waste/i,
      }) as HTMLButtonElement).disabled,
    ).toBe(false)
  })
})
