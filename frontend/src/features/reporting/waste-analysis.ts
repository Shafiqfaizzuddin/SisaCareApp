import type {
  WasteAnalysisFailure,
  WasteAnalysisResponse,
  WasteAnalysisSuccess,
} from '../../types'
import {
  authenticatedFetch,
  AuthenticatedRequestError,
} from '../authentication/authenticated-fetch'


const configuredAnalyzeUrl = import.meta.env.VITE_WASTE_ANALYSIS_URL as
  | string
  | undefined

export const WASTE_ANALYSIS_URL =
  configuredAnalyzeUrl?.trim() || '/api/waste/analyze'

export class WasteAnalysisRequestError extends Error {
  code?: string

  constructor(message: string, code?: string) {
    super(message)
    this.name = 'WasteAnalysisRequestError'
    this.code = code
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isFailure(value: unknown): value is WasteAnalysisFailure {
  return (
    isObject(value) &&
    value.success === false &&
    typeof value.code === 'string' &&
    typeof value.message === 'string'
  )
}

function isNumberRecord(value: unknown): value is Record<string, number> {
  return (
    isObject(value) &&
    Object.values(value).every(
      (item) =>
        typeof item === 'number' && Number.isInteger(item) && item >= 0,
    )
  )
}

function isDetection(value: unknown): boolean {
  if (!isObject(value) || !isObject(value.bounding_box)) return false
  const box = value.bounding_box
  return (
    typeof value.class_name === 'string' &&
    Number.isInteger(value.class_id) &&
    typeof value.confidence === 'number' &&
    Number.isFinite(value.confidence) &&
    value.confidence >= 0 &&
    value.confidence <= 1 &&
    typeof value.display_name === 'string' &&
    typeof value.waste_category === 'string' &&
    typeof value.material === 'string' &&
    typeof value.recyclable === 'boolean' &&
    typeof value.recommended_handling === 'string' &&
    [box.x1, box.y1, box.x2, box.y2].every(
      (coordinate) =>
        typeof coordinate === 'number' && Number.isFinite(coordinate),
    )
  )
}

function isReport(value: unknown): boolean {
  return (
    isObject(value) &&
    typeof value.title === 'string' &&
    typeof value.summary === 'string' &&
    typeof value.waste_identified === 'string' &&
    typeof value.recommended_action === 'string' &&
    typeof value.environmental_concern === 'string'
  )
}

function isSuccess(value: unknown): value is WasteAnalysisSuccess {
  return (
    isObject(value) &&
    value.success === true &&
    typeof value.analysis_id === 'string' &&
    typeof value.original_image === 'string' &&
    typeof value.annotated_image === 'string' &&
    isObject(value.detection) &&
    typeof value.detection.total_objects === 'number' &&
    Number.isInteger(value.detection.total_objects) &&
    value.detection.total_objects >= 0 &&
    isNumberRecord(value.detection.counts) &&
    Array.isArray(value.detection.detections) &&
    value.detection.detections.every(isDetection) &&
    isReport(value.report)
  )
}

async function readResponse(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    if (!response.ok) {
      throw new WasteAnalysisRequestError(
        `Waste analysis failed with status ${response.status}.`,
        'ANALYSIS_REQUEST_FAILED',
      )
    }
    throw new WasteAnalysisRequestError(
      'The analysis service returned an unreadable response.',
      'INVALID_API_RESPONSE',
    )
  }
}

export async function analyzeWasteImage(
  image: File,
  signal?: AbortSignal,
): Promise<WasteAnalysisSuccess> {
  const formData = new FormData()
  formData.append('image', image)

  let response: Response
  try {
    response = await authenticatedFetch(WASTE_ANALYSIS_URL, {
      method: 'POST',
      body: formData,
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    if (error instanceof AuthenticatedRequestError) {
      throw new WasteAnalysisRequestError(error.message, 'AUTHENTICATION_REQUIRED')
    }
    throw new WasteAnalysisRequestError(
      'The waste analysis service is unavailable. Please try again.',
      'ANALYSIS_UNAVAILABLE',
    )
  }

  const responseData: WasteAnalysisResponse | unknown = await readResponse(response)
  if (isFailure(responseData)) {
    throw new WasteAnalysisRequestError(responseData.message, responseData.code)
  }
  if (!response.ok) {
    throw new WasteAnalysisRequestError(
      `Waste analysis failed with status ${response.status}.`,
      'ANALYSIS_REQUEST_FAILED',
    )
  }
  if (!isSuccess(responseData)) {
    throw new WasteAnalysisRequestError(
      'The analysis service returned an unexpected result.',
      'INVALID_API_RESPONSE',
    )
  }

  const imageResponse = await authenticatedFetch(responseData.annotated_image, {
    signal,
  })
  if (!imageResponse.ok) {
    throw new WasteAnalysisRequestError(
      'The protected annotated image could not be loaded.',
      'ANNOTATED_IMAGE_UNAVAILABLE',
    )
  }
  const imageBlob = await imageResponse.blob()
  if (!imageBlob.type.startsWith('image/')) {
    throw new WasteAnalysisRequestError(
      'The analysis service returned an invalid annotated image.',
      'INVALID_ANNOTATED_IMAGE',
    )
  }
  if (signal?.aborted) {
    throw new DOMException('The analysis request was cancelled.', 'AbortError')
  }

  return {
    ...responseData,
    annotated_image: URL.createObjectURL(imageBlob),
  }
}
