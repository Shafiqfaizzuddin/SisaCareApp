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
  LocationPicker: () => <div>Location picker</div>,
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
