// @vitest-environment happy-dom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { analyzeWasteImage } from './waste-analysis'


const authMocks = vi.hoisted(() => ({
  authenticatedFetch: vi.fn(),
}))

vi.mock('../authentication/authenticated-fetch', () => ({
  authenticatedFetch: authMocks.authenticatedFetch,
  AuthenticatedRequestError: class AuthenticatedRequestError extends Error {},
}))

const ANALYSIS_RESPONSE = {
  success: true,
  analysis_id: 'draft-123',
  original_image: '/api/waste/uploads/upload.jpg',
  annotated_image: '/api/waste/annotated/annotated.jpg',
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
    title: 'Recyclable Waste Observation',
    summary: 'The analysis identifies recyclable waste.',
    waste_identified: 'Plastic Bottle (count: 1)',
    recommended_action: 'Recycling is recommended.',
    environmental_concern: 'Improper handling may contribute to litter.',
  },
}

beforeEach(() => {
  authMocks.authenticatedFetch.mockReset()
})

describe('analyzeWasteImage', () => {
  it('keeps a successful analysis visible when its annotated image cannot load', async () => {
    authMocks.authenticatedFetch
      .mockResolvedValueOnce(
        new Response(JSON.stringify(ANALYSIS_RESPONSE), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 403 }))

    const result = await analyzeWasteImage(
      new File(['image'], 'waste.jpg', { type: 'image/jpeg' }),
    )

    expect(result).toEqual({ ...ANALYSIS_RESPONSE, annotated_image: null })
    expect(authMocks.authenticatedFetch).toHaveBeenCalledTimes(2)
  })

  it('returns grouped results and the editable report when no annotation exists', async () => {
    authMocks.authenticatedFetch.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ ...ANALYSIS_RESPONSE, annotated_image: null }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    )

    const result = await analyzeWasteImage(
      new File(['image'], 'waste.jpg', { type: 'image/jpeg' }),
    )

    expect(result.report).toEqual(ANALYSIS_RESPONSE.report)
    expect(result.grouped_objects).toEqual(ANALYSIS_RESPONSE.grouped_objects)
    expect(authMocks.authenticatedFetch).toHaveBeenCalledOnce()
  })
})
