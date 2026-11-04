// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { analyzeWasteImage, WASTE_ANALYSIS_URL } from './waste-analysis'

const authMocks = vi.hoisted(() => ({ authenticatedFetch: vi.fn() }))
vi.mock('../authentication/authenticated-fetch', () => ({
  authenticatedFetch: authMocks.authenticatedFetch,
  AuthenticatedRequestError: class AuthenticatedRequestError extends Error {},
}))

const result = {
  success: true, analysis_id: 'draft-123', original_image: '/api/waste/uploads/upload.jpg',
  display_image: '/api/waste/annotated/oriented.jpg', image_width: 400, image_height: 300,
  provider: 'florence2', model_id: 'microsoft/Florence-2-base', model_revision: 'pinned',
  processing_time_ms: 500, warnings: [],
  detections: [{ id: 'det-0', label: 'bottle', name: 'bottle', display_name: 'Bottle',
    bounding_box: { x1: 10, y1: 20, x2: 100, y2: 200 }, confidence: null,
    review_status: 'needs_confirmation', suggested_category: null, material: 'Unknown', recommended_handling: 'Confirm disposal.' }],
}

beforeEach(() => authMocks.authenticatedFetch.mockReset())

describe('analyzeWasteImage', () => {
  it('calls the application backend and hides boxes if the aligned preview fails', async () => {
    authMocks.authenticatedFetch.mockResolvedValueOnce(new Response(JSON.stringify(result), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 403 }))
    const received = await analyzeWasteImage(new File(['image'], 'waste.jpg', { type: 'image/jpeg' }))
    expect(WASTE_ANALYSIS_URL).toBe('/api/waste/analyze')
    expect(authMocks.authenticatedFetch.mock.calls[0][0]).toBe('/api/waste/analyze')
    expect(received.display_image).toBeNull()
    expect(received.detections[0].confidence).toBeNull()
  })

  it('rejects out of bounds detections instead of drawing incorrect boxes', async () => {
    const invalid = { ...result, display_image: null, detections: [{ ...result.detections[0], bounding_box: { x1: 10, y1: 20, x2: 401, y2: 200 } }] }
    authMocks.authenticatedFetch.mockResolvedValueOnce(new Response(JSON.stringify(invalid), { status: 200 }))
    await expect(analyzeWasteImage(new File(['image'], 'waste.jpg', { type: 'image/jpeg' })))
      .rejects.toMatchObject({ code: 'INVALID_API_RESPONSE' })
  })

  it('accepts an evidence-count summary without treating confidence as share', async () => {
    const withSummary = { ...result, display_image: null, classification_summary: {
      version: '1.0.0', source: 'florence2_detections_plus_rules',
      denominator_definition: 'Non-background detections', total_detections: 2,
      background_excluded: 0, denominator: 2, unknown_count: 1, uncertain_count: 1,
      distribution: [{ category: 'Plastic', count: 1, percentage: 50 },
        { category: 'Unknown', count: 1, percentage: 50 }],
      dominant_category: 'Unknown', dominant_reason: 'Tied',
      severity: { level: 'Unknown', method: 'rule_based_handling_priority_v1', reason: 'Unresolved', is_physical_measurement: false },
      confidence: { florence_detection_score: null, category_probability: null, explanation: 'Unavailable' },
      limitations: [],
    } }
    authMocks.authenticatedFetch.mockResolvedValueOnce(new Response(JSON.stringify(withSummary), { status: 200 }))
    const received = await analyzeWasteImage(new File(['image'], 'waste.jpg', { type: 'image/jpeg' }))
    expect(received.classification_summary?.distribution[0]).toEqual({ category: 'Plastic', count: 1, percentage: 50 })
    expect(received.classification_summary?.confidence.category_probability).toBeNull()
  })

  it('rejects category percentages that disagree with detection counts', async () => {
    const invalid = { ...result, display_image: null, classification_summary: {
      total_detections: 1, background_excluded: 0, denominator: 1, unknown_count: 0, uncertain_count: 0,
      distribution: [{ category: 'Plastic', count: 1, percentage: 90 }], dominant_category: 'Plastic',
      severity: { level: 'Low', is_physical_measurement: false },
      confidence: { florence_detection_score: null, category_probability: null },
    } }
    authMocks.authenticatedFetch.mockResolvedValueOnce(new Response(JSON.stringify(invalid), { status: 200 }))
    await expect(analyzeWasteImage(new File(['image'], 'waste.jpg', { type: 'image/jpeg' })))
      .rejects.toMatchObject({ code: 'INVALID_API_RESPONSE' })
  })

  it('retains an honest Unknown summary when local visual fallback fails', async () => {
    const summary = { version: '1.0.0', source: 'florence2_detections_plus_rules',
      denominator_definition: 'Non-background detections', total_detections: 1,
      background_excluded: 0, denominator: 1, unknown_count: 1, uncertain_count: 1,
      distribution: [{ category: 'Unknown', count: 1, percentage: 100 }],
      dominant_category: 'Unknown', dominant_reason: 'Unresolved',
      severity: { level: 'Unknown', method: 'rule_based_handling_priority_v1', reason: 'Unresolved', is_physical_measurement: false },
      confidence: { florence_detection_score: null, category_probability: null, explanation: 'Unavailable' }, limitations: [] }
    authMocks.authenticatedFetch.mockResolvedValueOnce(new Response(JSON.stringify({
      success: false, code: 'VISION_UNAVAILABLE', message: 'Local vision unavailable', classification_summary: summary,
    }), { status: 503 }))
    await expect(analyzeWasteImage(new File(['image'], 'waste.jpg', { type: 'image/jpeg' })))
      .rejects.toMatchObject({ code: 'VISION_UNAVAILABLE', partialSummary: summary })
  })
})
