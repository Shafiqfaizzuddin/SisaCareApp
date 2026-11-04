import type { ClassificationSummary, FlorenceAnalysisSuccess, FlorenceDetection, WasteAnalysisFailure } from '../../types'
import { authenticatedFetch, AuthenticatedRequestError } from '../authentication/authenticated-fetch'

// The browser always calls the application backend. The backend owns the localhost service URL.
export const WASTE_ANALYSIS_URL = '/api/waste/analyze'

export class WasteAnalysisRequestError extends Error {
  code?: string
  partialSummary?: ClassificationSummary
  constructor(message: string, code?: string, partialSummary?: ClassificationSummary) {
    super(message)
    this.name = 'WasteAnalysisRequestError'
    this.code = code
    this.partialSummary = partialSummary
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function validDetection(value: unknown, width: number, height: number): value is FlorenceDetection {
  if (!record(value) || !record(value.bounding_box)) return false
  const { x1, y1, x2, y2 } = value.bounding_box
  return typeof value.id === 'string' && typeof value.label === 'string' &&
    typeof value.name === 'string' && typeof value.display_name === 'string' &&
    value.confidence === null &&
    ['likely_waste', 'background', 'needs_confirmation'].includes(value.review_status as string) &&
    (value.suggested_category === null || ['Recyclable Waste', 'Non-Recyclable Waste', 'Bulky Waste', 'Hazardous Waste'].includes(value.suggested_category as string)) &&
    typeof value.material === 'string' && typeof value.recommended_handling === 'string' &&
    [x1, y1, x2, y2].every((n) => typeof n === 'number' && Number.isFinite(n)) &&
    (x1 as number) >= 0 && (y1 as number) >= 0 && (x2 as number) <= width &&
    (y2 as number) <= height && (x2 as number) > (x1 as number) && (y2 as number) > (y1 as number)
}

const MATERIAL_CATEGORIES = new Set(['Organic', 'Plastic', 'Paper', 'Glass', 'Metal', 'Electronic', 'Hazardous', 'Other', 'Unknown'])

export function validSummary(value: unknown): value is ClassificationSummary {
  if (!record(value) || !Array.isArray(value.distribution) || !record(value.severity) || !record(value.confidence)) return false
  if (typeof value.version !== 'string' || value.source !== 'florence2_detections_plus_rules'
    || typeof value.denominator_definition !== 'string' || typeof value.dominant_reason !== 'string'
    || !Array.isArray(value.limitations) || !value.limitations.every(entry => typeof entry === 'string')
    || typeof value.severity.method !== 'string' || typeof value.severity.reason !== 'string'
    || typeof value.confidence.explanation !== 'string'
    || !Number.isInteger(value.total_detections) || !Number.isInteger(value.background_excluded)
    || !Number.isInteger(value.denominator) || !Number.isInteger(value.unknown_count)
    || !Number.isInteger(value.uncertain_count) || (value.denominator as number) < 0
    || (value.total_detections as number) < 0 || (value.background_excluded as number) < 0
    || (value.unknown_count as number) < 0 || (value.unknown_count as number) > (value.denominator as number)
    || (value.uncertain_count as number) < 0 || (value.uncertain_count as number) > (value.denominator as number)) return false
  const seen = new Set<string>()
  let total = 0
  for (const entry of value.distribution) {
    if (!record(entry) || typeof entry.category !== 'string' || !MATERIAL_CATEGORIES.has(entry.category)
      || seen.has(entry.category) || !Number.isInteger(entry.count) || (entry.count as number) <= 0
      || typeof entry.percentage !== 'number') return false
    seen.add(entry.category); total += entry.count as number
    if (Math.abs(entry.percentage - (entry.count as number) * 100 / (value.denominator as number)) > .051) return false
  }
  return total === value.denominator && (value.background_excluded as number) + (value.denominator as number) === value.total_detections
    && (seen.has('Unknown') ? value.distribution.find((entry: { category: string }) => entry.category === 'Unknown')?.count : 0) === value.unknown_count
    && typeof value.dominant_category === 'string' && MATERIAL_CATEGORIES.has(value.dominant_category)
    && ['Low', 'Medium', 'High', 'Unknown'].includes(value.severity.level as string)
    && value.severity.is_physical_measurement === false
    && value.confidence.florence_detection_score === null && value.confidence.category_probability === null
}

function validResult(value: unknown): value is FlorenceAnalysisSuccess {
  if (!record(value)) return false
  const width = value.image_width, height = value.image_height
  return value.success === true && typeof value.analysis_id === 'string' &&
    typeof value.original_image === 'string' &&
    (value.display_image === null || typeof value.display_image === 'string') &&
    Number.isInteger(width) && (width as number) > 0 && Number.isInteger(height) && (height as number) > 0 &&
    value.provider === 'florence2' && typeof value.model_id === 'string' &&
    typeof value.model_revision === 'string' &&
    Array.isArray(value.detections) && value.detections.every((d) => validDetection(d, width as number, height as number)) &&
    typeof value.processing_time_ms === 'number' && Array.isArray(value.warnings) &&
    value.warnings.every((warning) => typeof warning === 'string') &&
    (value.classification_summary === undefined || validSummary(value.classification_summary))
}

export async function analyzeWasteImage(image: File, signal?: AbortSignal): Promise<FlorenceAnalysisSuccess> {
  const form = new FormData()
  form.append('image', image)
  let response: Response
  try {
    response = await authenticatedFetch(WASTE_ANALYSIS_URL, { method: 'POST', body: form, signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    if (error instanceof AuthenticatedRequestError) {
      throw new WasteAnalysisRequestError(error.message, 'AUTHENTICATION_REQUIRED')
    }
    throw new WasteAnalysisRequestError('Local photo analysis is unavailable. You can identify items manually.', 'FLORENCE_UNAVAILABLE')
  }
  let data: unknown
  try {
    data = await response.json()
  } catch {
    throw new WasteAnalysisRequestError('The analysis service returned an unreadable response.', 'INVALID_API_RESPONSE')
  }
  if (record(data) && data.success === false && typeof data.message === 'string') {
    const failure = data as unknown as WasteAnalysisFailure
    throw new WasteAnalysisRequestError(failure.message, failure.code,
      validSummary(data.classification_summary) ? data.classification_summary : undefined)
  }
  if (!response.ok || !validResult(data)) {
    throw new WasteAnalysisRequestError('The analysis service returned an unexpected result.', 'INVALID_API_RESPONSE')
  }
  if (!data.display_image) return data
  try {
    const display = await authenticatedFetch(data.display_image, { signal })
    if (display.ok) {
      const blob = await display.blob()
      if (blob.type.startsWith('image/')) return { ...data, display_image: URL.createObjectURL(blob) }
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
  }
  return { ...data, display_image: null, warnings: [...data.warnings, 'Aligned image preview unavailable; bounding boxes are hidden.'] }
}
