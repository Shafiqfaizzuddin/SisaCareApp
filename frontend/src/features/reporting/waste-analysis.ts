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

const finalCategories = new Set([
  'Non-Recyclable',
  'Recyclable Waste',
  'Bulky Waste',
  'Unknown',
])

function isBoundingBoxOrNull(value: unknown): boolean {
  if (value === null) return true
  if (!isObject(value)) return false
  return [value.x1, value.y1, value.x2, value.y2].every(
    (coordinate) => typeof coordinate === 'number' && Number.isFinite(coordinate),
  )
}

function isFusedObject(value: unknown): boolean {
  return (
    isObject(value) &&
    typeof value.name === 'string' &&
    typeof value.display_name === 'string' &&
    finalCategories.has(value.category as string) &&
    ['mapping', 'vlm', 'unknown'].includes(value.category_source as string) &&
    ['yolo', 'vlm', 'yolo+vlm'].includes(value.source as string) &&
    (value.confidence === null || typeof value.confidence === 'number') &&
    (value.confidence_level === null ||
      ['high', 'medium', 'low'].includes(value.confidence_level as string)) &&
    typeof value.supported_by_vlm === 'boolean' &&
    isBoundingBoxOrNull(value.bounding_box)
  )
}

function isGroupedObject(value: unknown): boolean {
  return (
    isObject(value) &&
    typeof value.name === 'string' &&
    typeof value.label === 'string' &&
    (value.count === null ||
      (Number.isInteger(value.count) && (value.count as number) >= 1)) &&
    finalCategories.has(value.category as string) &&
    Array.isArray(value.sources) &&
    value.sources.every((source) => source === 'yolo' || source === 'vlm') &&
    (value.average_yolo_confidence === null ||
      typeof value.average_yolo_confidence === 'number')
  )
}

function isReport(value: unknown): boolean {
  return (
    isObject(value) &&
    Object.keys(value).length === 5 &&
    [
      value.title,
      value.summary,
      value.waste_identified,
      value.recommended_action,
      value.environmental_concern,
    ].every((field) => typeof field === 'string' && field.trim().length > 0)
  )
}

function isSuccess(value: unknown): value is WasteAnalysisSuccess {
  return (
    isObject(value) &&
    value.success === true &&
    typeof value.analysis_id === 'string' &&
    typeof value.original_image === 'string' &&
    (value.annotated_image === null || typeof value.annotated_image === 'string') &&
    Array.isArray(value.detections) &&
    value.detections.every(isFusedObject) &&
    Array.isArray(value.grouped_objects) &&
    value.grouped_objects.every(isGroupedObject) &&
    Array.isArray(value.categories_detected) &&
    value.categories_detected.every((category) =>
      finalCategories.has(category as string),
    ) &&
    typeof value.scene_description === 'string' &&
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

  if (responseData.annotated_image) {
    try {
      const imageResponse = await authenticatedFetch(responseData.annotated_image, {
        signal,
      })
      if (imageResponse.ok) {
        const imageBlob = await imageResponse.blob()
        if (imageBlob.type.startsWith('image/')) {
          if (signal?.aborted) {
            throw new DOMException('The analysis request was cancelled.', 'AbortError')
          }
          return {
            ...responseData,
            annotated_image: URL.createObjectURL(imageBlob),
          }
        }
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw error
      }
    }

    return {
      ...responseData,
      annotated_image: null,
    }
  }

  return responseData
}
